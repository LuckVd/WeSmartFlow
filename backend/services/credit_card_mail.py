"""Persisted card email delivery; retries reuse the card and recipient snapshot."""

import html
import json
import re
import smtplib
import ssl
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import urlsplit

from config import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    SMTP_FROM_NAME,
    PUBLIC_BASE_URL,
)
from database import get_db

LEASE_SECONDS = 180


class CardMailError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def check_mail_config():
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD]):
        raise CardMailError("邮件服务未配置，请先配置 SMTP 后再发送")


def recipient(conn, user_id):
    row = conn.execute(
        "SELECT id,name,email FROM users WHERE id=? AND id!='__system__'", (user_id,)
    ).fetchone()
    if not row:
        raise CardMailError("所选用户不存在")
    email = (row["email"] or "").strip()
    if not re.fullmatch(r"[^\s@<>;,]+@[^\s@<>;,]+\.[^\s@<>;,]+", email):
        raise CardMailError("所选用户没有有效邮箱，请选择其他用户")
    return {"user_id": row["id"], "name": row["name"], "email": email}


def public_delivery(row):
    if not row:
        return None
    result = {
        key: row[key]
        for key in (
            "card_id",
            "request_id",
            "recipient_user_id",
            "recipient_email",
            "status",
            "attempts",
            "last_error",
            "created_at",
            "updated_at",
            "sent_at",
        )
    }
    if result["status"] in ("queued", "sending"):
        cutoff = (
            datetime.now(timezone.utc) - timedelta(seconds=LEASE_SECONDS)
        ).isoformat()
        if result["updated_at"] < cutoff:
            result["status"] = "unknown"
            result["last_error"] = (
                "发送任务可能中断，状态不明；请确认收件箱后重试同一兑换码"
            )
    return result


def get_delivery(card_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM credit_card_email_deliveries WHERE card_id=?", (card_id,)
        ).fetchone()
        if not row:
            raise CardMailError("没有该卡的邮件发送记录")
        return public_delivery(row)


def find_delivery_request(conn, request_id):
    row = conn.execute(
        "SELECT * FROM credit_card_email_deliveries WHERE request_id=?", (request_id,)
    ).fetchone()
    if row:
        return row
    row = conn.execute(
        "SELECT delivery_json FROM credit_card_email_history WHERE request_id=?",
        (request_id,),
    ).fetchone()
    return json.loads(row["delivery_json"]) if row else None


def gift_card(card_id, user_id, request_id):
    """Queue an existing code; retain prior recipients and deduplicate submissions."""
    check_mail_config()
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = find_delivery_request(conn, request_id)
        if existing:
            if (
                existing["card_id"] != card_id
                or existing["recipient_user_id"] != user_id
            ):
                raise CardMailError("请求已处理，请重新打开赠送面板")
            return public_delivery(existing)
        card = conn.execute(
            "SELECT * FROM credit_cards WHERE code_hash=?", (card_id,)
        ).fetchone()
        _check_card(card)
        selected = recipient(conn, user_id)
        if conn.execute(
            "SELECT 1 FROM credit_card_redemptions WHERE code_hash=? AND user_id=?",
            (card_id, user_id),
        ).fetchone():
            raise CardMailError("该用户已兑换过这张积分卡，请选择其他用户")
        previous = conn.execute(
            "SELECT * FROM credit_card_email_deliveries WHERE card_id=?", (card_id,)
        ).fetchone()
        if previous:
            if public_delivery(previous)["status"] in ("queued", "sending"):
                raise CardMailError("这张卡的邮件正在发送，请稍后再赠送")
            conn.execute(
                "INSERT INTO credit_card_email_history VALUES (?,?,?)",
                (previous["request_id"], card_id, json.dumps(dict(previous))),
            )
            conn.execute(
                "DELETE FROM credit_card_email_deliveries WHERE card_id=?", (card_id,)
            )
        timestamp = _now()
        conn.execute(
            """INSERT INTO credit_card_email_deliveries
            (card_id,request_id,recipient_user_id,recipient_name,recipient_email,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?)""",
            (
                card_id,
                request_id,
                user_id,
                selected["name"],
                selected["email"],
                timestamp,
                timestamp,
            ),
        )
        return public_delivery(
            conn.execute(
                "SELECT * FROM credit_card_email_deliveries WHERE card_id=?", (card_id,)
            ).fetchone()
        )


def _check_card(card):
    if not card or not card["code_plain"]:
        raise CardMailError("积分卡不存在或没有可发送的兑换码")
    if card["disabled"]:
        raise CardMailError("积分卡已停用，不能发送")
    if (
        card["max_redemptions"] > 0
        and card["redeemed_count"] >= card["max_redemptions"]
    ):
        raise CardMailError("积分卡已兑完，不能发送")
    if card["expires_at"]:
        try:
            expiry = datetime.fromisoformat(card["expires_at"].replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                raise ValueError("missing timezone")
        except ValueError as exc:
            raise CardMailError("积分卡有效期格式不正确，不能发送") from exc
        if expiry <= datetime.now(timezone.utc):
            raise CardMailError("积分卡已过期，不能发送")


def retry_delivery(card_id):
    check_mail_config()
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM credit_card_email_deliveries WHERE card_id=?", (card_id,)
        ).fetchone()
        if not row:
            raise CardMailError("没有该卡的邮件发送记录")
        if public_delivery(row)["status"] in ("queued", "sending"):
            raise CardMailError("邮件正在发送，请稍后查看结果")
        _check_card(
            conn.execute(
                "SELECT * FROM credit_cards WHERE code_hash=?", (card_id,)
            ).fetchone()
        )
        conn.execute(
            "UPDATE credit_card_email_deliveries SET status='queued',last_error='',updated_at=?,attempt_id='' WHERE card_id=?",
            (_now(), card_id),
        )
    return get_delivery(card_id)


def build_message(card, delivery):
    message = EmailMessage()
    message["From"] = f"{SMTP_FROM_NAME} <{SMTP_USER}>"
    message["To"] = delivery["recipient_email"]
    message["Subject"] = f"【{SMTP_FROM_NAME}】您的积分兑换卡"
    # Retries share an ID; separate gifts to different recipients do not.
    message["Message-ID"] = (
        f"<credit-card-{uuid.uuid5(uuid.NAMESPACE_URL, delivery['request_id']).hex}@{SMTP_USER.split('@')[-1]}>"
    )
    mode = "增加积分" if card["mode"] == "add" else "将账户余额重置为"
    instructions = f"{mode} {card['amount']:,} 积分"
    warning = (
        "\n注意：这是一张重置卡，兑换后会覆盖原有余额，可能减少已有积分。"
        if card["mode"] == "reset"
        else ""
    )
    expiry = (
        f"\n有效期至：{card['expires_at']}"
        if card["expires_at"]
        else "\n有效期：未设置到期时间"
    )
    base = PUBLIC_BASE_URL.rstrip("/")
    parts = urlsplit(base)
    link = (
        base + "/#/settings"
        if parts.scheme in ("https", "http")
        and parts.netloc
        and not parts.query
        and not parts.fragment
        else ""
    )
    action = f"前往 {link}" if link else f"登录 {SMTP_FROM_NAME}"
    text = f"您好，{delivery['recipient_name']}：\n\n您收到一张积分兑换卡。\n{instructions}\n兑换码：{card['code_plain']}{expiry}{warning}\n\n{action}，在设置页「兑换积分卡」中输入兑换码。\n发送邮件不会自动兑换；每个账号对同一卡码只能兑换一次。请妥善保管兑换码。"
    message.set_content(text)
    brand = html.escape(SMTP_FROM_NAME)
    name = html.escape(delivery["recipient_name"] or "同学")
    code = html.escape(card["code_plain"])
    button = (
        f'<p style="margin:24px 0;text-align:center;"><a href="{html.escape(link, quote=True)}" style="display:inline-block;background:#6366f1;color:#ffffff;text-decoration:none;padding:14px 28px;border-radius:10px;font-size:15px;font-weight:600;">前往设置页兑换</a></p>'
        if link
        else ""
    )
    warning_html = (
        '<p style="margin:20px 0;padding:14px;background:#fffbeb;border:1px solid #fde68a;border-radius:10px;color:#92400e;font-size:13px;line-height:1.8;">'
        + html.escape(warning.strip())
        + "</p>"
        if warning
        else ""
    )
    message.add_alternative(
        f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:24px 12px;background:#f5f5fa;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;margin:0 auto;table-layout:fixed;">
<tr><td style="background:#6366f1;background-image:linear-gradient(135deg,#6366f1,#a855f7);padding:32px 24px;border-radius:16px 16px 0 0;text-align:center;">
  <h1 style="color:#fff;margin:0;font-size:24px;font-weight:700;overflow-wrap:anywhere;">{brand}</h1>
  <p style="color:#ede9fe;margin:8px 0 0;font-size:14px;">你的专属知识大脑</p>
</td></tr>
<tr><td style="background:#fff;padding:28px 24px;border:1px solid #e5e7eb;border-top:none;">
  <p style="color:#374151;font-size:15px;line-height:1.8;margin:0 0 8px;overflow-wrap:anywhere;">您好，{name}：</p>
  <h2 style="color:#111827;font-size:21px;margin:0 0 20px;">您收到一张积分兑换卡</h2>
  <div style="background:#f5f3ff;border:1px solid #ede9fe;border-radius:12px;padding:24px 16px;text-align:center;">
    <p style="color:#6b7280;font-size:13px;margin:0 0 8px;">{mode}</p>
    <p style="color:#6366f1;font-size:30px;font-weight:700;margin:0;overflow-wrap:anywhere;">{card["amount"]:,}<span style="font-size:14px;font-weight:400;"> 积分</span></p>
    <p style="color:#6b7280;font-size:12px;margin:22px 0 8px;">积分兑换码</p>
    <p style="color:#312e81;font-family:Consolas,monospace;font-size:18px;font-weight:700;line-height:1.6;margin:0;word-break:normal;overflow-wrap:anywhere;">{code}</p>
  </div>
  <p style="color:#6b7280;font-size:12px;line-height:1.8;margin:12px 0 0;">{html.escape(expiry.strip())}</p>
  {warning_html}
  <h3 style="color:#374151;font-size:14px;margin:24px 0 10px;">如何兑换</h3>
  <p style="color:#6b7280;font-size:13px;line-height:1.9;margin:0;">1. 登录 {brand}，打开设置页。<br>2. 在「兑换积分卡」中粘贴上方兑换码。<br>3. 确认兑换后，积分将更新到您的账户。</p>
  {button}
  <p style="color:#9ca3af;font-size:12px;line-height:1.8;margin:20px 0 0;">发送邮件不会自动兑换；每个账号对同一卡码只能兑换一次。请妥善保管兑换码。</p>
</td></tr>
<tr><td style="padding:18px 24px;text-align:center;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 16px 16px;background:#f9fafb;">
  <p style="color:#9ca3af;font-size:12px;line-height:1.8;margin:0;">来自 {brand} 的学习赠礼<br>此邮件由系统发送，请勿直接回复。</p>
</td></tr></table></body></html>""",
        subtype="html",
    )
    return message


def _send_smtp(message):
    check_mail_config()
    if SMTP_PORT == 465:
        server = smtplib.SMTP_SSL(
            SMTP_HOST, SMTP_PORT, timeout=10, context=ssl.create_default_context()
        )
    else:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
    with server:
        if SMTP_PORT != 465:
            server.starttls(context=ssl.create_default_context())
        server.login(SMTP_USER, SMTP_PASSWORD)
        refused = server.send_message(message)
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)


def send_card_email(card_id, request_id=None):
    attempt_id = uuid.uuid4().hex
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        claimed = conn.execute(
            "UPDATE credit_card_email_deliveries SET status='sending',attempts=attempts+1,attempt_id=?,updated_at=? WHERE card_id=? AND status='queued' AND (? IS NULL OR request_id=?)",
            (attempt_id, _now(), card_id, request_id, request_id),
        )
        if not claimed.rowcount:
            return
        delivery = dict(
            conn.execute(
                "SELECT * FROM credit_card_email_deliveries WHERE card_id=?", (card_id,)
            ).fetchone()
        )
        row = conn.execute(
            "SELECT * FROM credit_cards WHERE code_hash=?", (card_id,)
        ).fetchone()
        card = dict(row) if row else None
    status, error = "sent", ""
    try:
        _check_card(card)
        _send_smtp(build_message(card, delivery))
    except CardMailError as exc:
        status, error = "failed", str(exc)
    except smtplib.SMTPAuthenticationError:
        status, error = "failed", "SMTP 认证失败，请检查邮件账号配置后重试"
    except smtplib.SMTPRecipientsRefused:
        status, error = "failed", "邮件服务器拒绝收件地址，请检查邮箱"
    except Exception:
        # SMTP can accept DATA before the connection drops; never promise non-delivery.
        status, error = (
            "unknown",
            "未确认发送结果，请检查收件箱及 SMTP 服务后重试同一兑换码",
        )
    with get_db() as conn:
        conn.execute(
            "UPDATE credit_card_email_deliveries SET status=?,last_error=?,updated_at=?,sent_at=CASE WHEN ?='sent' THEN ? ELSE sent_at END WHERE card_id=? AND attempt_id=?",
            (status, error, _now(), status, _now(), card_id, attempt_id),
        )
