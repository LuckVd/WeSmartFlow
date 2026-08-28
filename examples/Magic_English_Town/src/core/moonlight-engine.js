import { getSceneAccess } from "./scene-unlocks.js";

const LOCATION_NAMES = {
  town: "Town Square",
  bakery: "Moonbeam Bakery",
  school: "Star School",
  park: "Whispering Park",
  storyhouse: "Story House",
};

const TASKS = ["bakery", "school", "park"];
const COLORS = ["blue", "yellow", "purple"];
const SHAPES = ["star", "moon", "circle"];
const FOODS = ["cookie", "cake", "bread"];
const INVITEES = ["Betty", "Ms. Maple", "Coco"];

export const FESTIVAL_RELICS = {
  bakery: {
    icon: "🍰",
    magic: "Kindness Magic",
    relic: "Sharing Moon Cake",
    surprise: "Tap Betty's festival table in the Square to reveal its secret message.",
  },
  school: {
    icon: "🎏",
    magic: "Color Magic",
    relic: "Moon Ribbon",
    surprise: "Tap your flags in the Square to send a shooting star across the sky.",
  },
  park: {
    icon: "✨",
    magic: "Light Magic",
    relic: "Firefly Constellation",
    surprise: "Tap the fireflies in the Square to discover the shape they remember.",
  },
};

export const FESTIVAL_CHALLENGES = {
  bakery: "bakery-kindness",
  school: "school-colors",
  park: "park-fireflies",
};

function clean(value) {
  return String(value ?? "").trim().toLowerCase().replace(/[’]/g, "'").replace(/[^a-z0-9\u3400-\u9fff'\s-]/g, " ").replace(/\s+/g, " ");
}

function includesAny(text, words) {
  return words.some((word) => text.includes(word));
}

function numberFromText(text) {
  if (includesAny(text, ["three", "3", "三"] )) return 3;
  if (includesAny(text, ["two", "2", "二", "两"] )) return 2;
  return 1;
}

function picked(text, values, fallback) {
  return values.find((value) => text.includes(value)) ?? fallback;
}

export function createMoonlightState(story, lessonOneMemory = null) {
  return {
    storyId: story.id,
    storyTitle: story.title,
    storyRuntime: story.runtime,
    storyPremise: story.agent?.premise ?? "",
    storyStages: [...(story.progression?.stages ?? ["bridge", "prepare", "finale", "celebration"])],
    sceneUnlocks: story.world?.sceneUnlocks ?? {},
    phase: "bridge",
    location: story.world?.startLocation ?? "town",
    time: "sunset",
    busy: false,
    completedTasks: new Set(),
    visited: new Set([story.world?.startLocation ?? "town"]),
    englishTurns: [],
    evidence: Object.fromEntries((story.learning?.outcomes ?? []).map((outcome) => [outcome.id, new Set()])),
    samples: Object.fromEntries((story.learning?.outcomes ?? []).map((outcome) => [outcome.id, []])),
    stars: 0,
    treats: { food: "cookie", quantity: 2, forWhom: "everyone" },
    flag: { color: "blue", shape: "star", count: 3, described: false },
    fireflies: new Set(),
    surprisesFound: new Set(),
    learning: {
      activeId: null,
      questionIndex: 0,
      feedback: null,
      correct: false,
      finished: false,
      voiceHeard: "",
      hintOpen: false,
      attempts: {},
      completed: new Set(),
    },
    selectedInvitee: "Coco",
    invited: new Set(),
    finalInstruction: "",
    memoryStep: 0,
    memoryDraftLines: Array.from({ length: story.writing?.scenes?.length ?? 4 }, () => ""),
    memoryLines: Array.from({ length: story.writing?.scenes?.length ?? 4 }, () => ""),
    memoryEdited: new Set(),
    memoryBookComplete: false,
    lessonOneMemory,
    history: [],
    guide: {
      speaker: "Coco",
      reply: lessonOneMemory?.complete ? "You helped me home. Tonight, let's help the whole town!" : "I'm so happy you're here. Will you explore the evening town with me?",
      hint: "Close the storybook and step into the sunset.",
    },
    lastResult: null,
  };
}

export function startMoonlightLesson(state) {
  state.phase = "prepare";
  state.time = "twilight";
  state.location = "town";
  state.guide = {
    speaker: "Milo",
    reply: "Coco's welcome-home festival cannot begin—the Moon Lantern has forgotten how to shine.",
    hint: "Bring back Kindness, Color, and Light in story order. Begin with the Bakery.",
  };
  return state;
}

export function visitMoonlightLocation(state, location) {
  if (!Object.hasOwn(LOCATION_NAMES, location)) return false;
  if (!getSceneAccess(state, location).unlocked) return false;
  state.location = location;
  state.visited.add(location);
  const guides = {
    town: ["Milo", state.phase === "finale" ? "Everything you made is here. Invite a friend, then tell us how to finish." : "The dark Moon Lantern is waiting for three kinds of town magic."],
    bakery: ["Betty", state.completedTasks.has("bakery") ? "Your treats are ready for the festival table!" : "Choose a treat and ask for it kindly in your own words."],
    school: ["Ms. Maple", state.completedTasks.has("school") ? "Your flag is already dancing in the evening breeze." : "Design a flag, then describe its color and shape."],
    park: ["Coco", state.completedTasks.has("park") ? "The fireflies remember your directions!" : "This old tree feels different now. Let's find three fireflies and guide them together."],
    storyhouse: ["Milo", "The first story is still on the shelf, and a new moonlit page is waiting."],
  };
  const [speaker, reply] = guides[location];
  state.guide = { speaker, reply, hint: moonlightPrompt(state) };
  return true;
}

export function selectTreat(state, food, quantity = state.treats.quantity) {
  if (state.location !== "bakery" || !getSceneAccess(state, "bakery").unlocked || !FOODS.includes(food)) return false;
  state.treats.food = food;
  state.treats.quantity = Math.max(1, Math.min(3, Number(quantity) || 1));
  return true;
}

export function selectFlagPart(state, type, value) {
  if (state.location !== "school" || !getSceneAccess(state, "school").unlocked) return false;
  if (type === "color" && COLORS.includes(value)) state.flag.color = value;
  else if (type === "shape" && SHAPES.includes(value)) state.flag.shape = value;
  else return false;
  return true;
}

export function discoverFirefly(state, id) {
  if (state.location !== "park" || !getSceneAccess(state, "park").unlocked || !["tree", "bush", "fountain"].includes(id)) return false;
  const before = state.fireflies.size;
  state.fireflies.add(id);
  if (state.fireflies.size > before) state.stars += 1;
  return state.fireflies.size > before;
}

export function selectInvitee(state, invitee) {
  if (state.location !== "town" || state.phase !== "finale" || !INVITEES.includes(invitee)) return false;
  state.selectedInvitee = invitee;
  return true;
}

function addEvidence(state, outcome, token, text, source) {
  state.evidence[outcome] ??= new Set();
  state.samples[outcome] ??= [];
  if (state.evidence[outcome].has(token)) return false;
  state.evidence[outcome].add(token);
  if (text) state.samples[outcome].push({ text, source });
  return true;
}

function addEnglishTurn(state, message, source, intent) {
  if (!["text", "voice"].includes(source) || clean(message).split(" ").filter(Boolean).length < 2) return;
  state.englishTurns.push({ text: String(message).trim(), source, intent, location: state.location, phase: state.phase });
}

function completeTask(state, task) {
  if (!TASKS.includes(task) || state.completedTasks.has(task)) return false;
  state.completedTasks.add(task);
  state.stars += 3;
  if (state.completedTasks.size === TASKS.length) {
    state.phase = "finale";
    state.time = "twilight";
  }
  return true;
}

export function festivalProgress(state) {
  const taskCount = TASKS.filter((task) => state.completedTasks.has(task)).length;
  const invited = state.invited.size > 0;
  const lit = state.phase === "celebration";
  return {
    taskCount,
    totalTasks: TASKS.length,
    invited,
    lit,
    percent: lit ? 100 : Math.round(((taskCount + (invited ? 1 : 0)) / 5) * 100),
    readyForFinale: taskCount === TASKS.length,
  };
}

export function festivalRewardProgress(state) {
  const earned = TASKS.filter((task) => state.completedTasks.has(task));
  const unlocked = earned.filter((task) => state.learning?.completed?.has(FESTIVAL_CHALLENGES[task]));
  const found = unlocked.filter((task) => state.surprisesFound.has(task));
  return {
    earned,
    unlocked,
    found,
    remaining: unlocked.filter((task) => !state.surprisesFound.has(task)),
    total: TASKS.length,
  };
}

export function festivalQuest(state) {
  const completed = TASKS.filter((task) => state.completedTasks.has(task));
  const missing = TASKS.filter((task) => !state.completedTasks.has(task));
  const questByLocation = {
    bakery: {
      kicker: "KINDNESS MAGIC · SHARE SOMETHING",
      title: "Prepare a welcome treat",
      story: "Betty can fill the first lantern mark with kindness, but the sharing basket only glows after a polite English request.",
    },
    school: {
      kicker: "COLOR MAGIC · MAKE SOMETHING",
      title: "Create Coco's welcome flag",
      story: "Ms. Maple saved a blank flag for Coco. Give it a color and shape, then describe your design in English.",
    },
    park: {
      kicker: "LIGHT MAGIC · GUIDE SOMETHING",
      title: "Lead the fireflies home",
      story: "Three fireflies are hiding near the old tree. Find them, then use First and then to guide their light back to town.",
    },
  };
  if (state.phase === "celebration") return {
    chapter: 5,
    totalChapters: 5,
    kicker: "THE MOONLIGHT FESTIVAL",
    title: "The Moon Lantern is awake!",
    story: "Kindness, Color, Light, and your invitation became one living festival because of your English.",
    targetLocation: "town",
    cta: "Explore the celebration",
    complete: true,
  };
  if (completed.length < TASKS.length) {
    const currentTask = TASKS.includes(state.location) && !state.completedTasks.has(state.location) ? state.location : null;
    const targetLocation = currentTask ?? missing[0];
    const quest = questByLocation[targetLocation];
    return {
      chapter: completed.length + 1,
      totalChapters: 5,
      kicker: `STORY STEP ${completed.length + 1} OF 5 · ${quest.kicker}`,
      title: quest.title,
      story: quest.story,
      targetLocation,
      cta: state.location === targetLocation ? "Continue this story step" : `Go to ${LOCATION_NAMES[targetLocation]}`,
      complete: false,
    };
  }
  if (state.location !== "town") return {
    chapter: 4,
    totalChapters: 5,
    kicker: "STORY STEP 4 OF 5 · BRING EVERYONE TOGETHER",
    title: "Carry the three magics to the Square",
    story: "The treats, flag, and fireflies are ready. Coco can see one empty place beside the Moon Lantern.",
    targetLocation: "town",
    cta: "Return to Town Square",
    complete: false,
  };
  if (!state.invited.size) return {
    chapter: 4,
    totalChapters: 5,
    kicker: "STORY STEP 4 OF 5 · ONE EMPTY PLACE",
    title: "Invite a friend to the festival",
    story: "The table is set and the flag is flying, but Coco notices an empty place. Moonlight grows brighter when it is shared.",
    targetLocation: "town",
    cta: `Invite ${state.selectedInvitee}`,
    complete: false,
  };
  return {
    chapter: 5,
    totalChapters: 5,
    kicker: "STORY STEP 5 OF 5 · YOUR ENGLISH LIGHT",
    title: "Wake the Moon Lantern",
    story: "Everyone is ready. The lantern is listening for your final two-step English plan: what happens first, and what happens next.",
    targetLocation: "town",
    cta: "Build the lighting plan",
    complete: false,
  };
}

export function discoverFestivalSurprise(state, id) {
  const challengeId = FESTIVAL_CHALLENGES[id];
  if (!TASKS.includes(id)
    || state.location !== "town"
    || !state.completedTasks.has(id)
    || !state.learning?.completed?.has(challengeId)
    || state.surprisesFound.has(id)) return false;
  state.surprisesFound.add(id);
  state.stars += 2;
  return true;
}

export function festivalOutcomeProgress(state, story) {
  return (story.learning?.outcomes ?? []).map((outcome) => {
    const parts = outcome.criteria.map((criterion) => {
      const count = [...(state.evidence[outcome.id] ?? [])].filter((token) => token.startsWith(criterion.prefix)).length;
      return { ...criterion, count: Math.min(count, criterion.required), complete: count >= criterion.required };
    });
    return { ...outcome, parts, complete: parts.every((part) => part.complete), samples: state.samples[outcome.id] ?? [] };
  });
}

export function festivalTaskGuide(state) {
  const completed = TASKS.filter((task) => state.completedTasks.has(task));
  const missing = TASKS.filter((task) => !state.completedTasks.has(task));
  const taskNames = { bakery: "Kindness Magic", school: "Color Magic", park: "Light Magic" };
  const taskIcons = { bakery: "🥐", school: "☆", park: "✨", town: "☾" };

  if (state.phase === "celebration") return {
    kind: "complete",
    icon: "✨",
    eyebrow: "MAIN STORY COMPLETE · 5/5",
    title: "The Moon Lantern is awake!",
    detail: "You restored all three magics, invited a friend, and gave the final plan.",
    example: "Open your moonlight memory, or keep exploring the festival.",
    actionLabel: "YOU DID IT",
    progress: "5/5 story steps",
    steps: ["Three magics restored", "Friend invited", "Lantern lit"],
    targetLocation: "town",
  };

  if (completed.length < TASKS.length) {
    const currentTask = TASKS.includes(state.location) && !state.completedTasks.has(state.location) ? state.location : null;
    const targetLocation = currentTask ?? missing[0];
    if (state.location !== targetLocation) return {
      kind: "travel",
      icon: taskIcons[targetLocation],
      eyebrow: `STORY STEP ${completed.length + 1} OF 5 · ${taskNames[targetLocation].toUpperCase()}`,
      title: `Go to ${LOCATION_NAMES[targetLocation]}`,
      detail: `${taskNames[targetLocation]} is the next recommended story stop. Choose the highlighted place, or say where you want to go.`,
      example: `Let's go to ${LOCATION_NAMES[targetLocation]}.`,
      actionLabel: "YOU CAN ALSO SAY",
      progress: `${completed.length}/3 magics ready`,
      steps: [`1 · Enter ${LOCATION_NAMES[targetLocation]}`, "2 · Look, choose, then use English"],
      targetLocation,
    };
    if (targetLocation === "bakery") return {
      kind: "speak",
      icon: taskIcons.bakery,
      eyebrow: `STORY STEP ${completed.length + 1} OF 5 · KINDNESS MAGIC`,
      title: "Fill the sharing basket",
      detail: "Choose a treat and amount for everyone, then make one polite English request. Your own words wake Kindness Magic.",
      example: `Can I have ${state.treats.quantity} ${state.treats.food}${state.treats.quantity > 1 ? "s" : ""}, please?`,
      actionLabel: "TRY SAYING",
      progress: "Request needed",
      steps: ["1 · Choose food + number", "2 · Ask Betty with please"],
      targetLocation,
    };
    if (targetLocation === "school") return {
      kind: "speak",
      icon: taskIcons.school,
      eyebrow: `STORY STEP ${completed.length + 1} OF 5 · COLOR MAGIC`,
      title: "Make Coco's welcome flag",
      detail: "Choose one color and one shape, then describe both details in English. Your design wakes Color Magic.",
      example: `My flag is ${state.flag.color}. It has a ${state.flag.shape} on it.`,
      actionLabel: "TRY SAYING",
      progress: "Description needed",
      steps: ["1 · Choose color + shape", "2 · Describe both details"],
      targetLocation,
    };
    if (state.fireflies.size < 3) return {
      kind: "tap",
      icon: taskIcons.park,
      eyebrow: `STORY STEP ${completed.length + 1} OF 5 · LIGHT MAGIC`,
      title: `Find ${3 - state.fireflies.size} more firefl${3 - state.fireflies.size === 1 ? "y" : "ies"}`,
      detail: "Find the three glowing ? markers near the old tree. After all three appear, your English directions can lead them home.",
      example: "I found a firefly behind the tree.",
      actionLabel: "YOU CAN ALSO SAY",
      progress: `${state.fireflies.size}/3 found`,
      steps: ["1 · Tap all 3 glowing lights", "2 · Then give two directions"],
      targetLocation,
    };
    return {
      kind: "speak",
      icon: taskIcons.park,
      eyebrow: `STORY STEP ${completed.length + 1} OF 5 · LIGHT MAGIC`,
      title: "Lead the fireflies back to town",
      detail: "All three lights found you. Use First and then in one English sentence to give them a safe route home.",
      example: "First fly to the fountain, then go to the lantern.",
      actionLabel: "TRY SAYING",
      progress: "3/3 found · directions needed",
      steps: ["✓ All 3 fireflies found", "2 · Say First…, then…"],
      targetLocation,
    };
  }

  if (state.location !== "town") return {
    kind: "travel",
    icon: taskIcons.town,
    eyebrow: "STORY STEP 4 OF 5 · THREE MAGICS READY",
    title: "Return to Town Square",
    detail: "The sharing basket, welcome flag, and fireflies are ready. Bring all three back to Coco and the Moon Lantern.",
    example: "Let's go back to Town Square.",
    actionLabel: "YOU CAN ALSO SAY",
    progress: "3/3 magics",
    steps: ["✓ Collect three magics", "2 · Return to the Square"],
    targetLocation: "town",
  };

  if (!state.invited.size) return {
    kind: "speak",
    icon: "💌",
    eyebrow: "STORY STEP 4 OF 5 · INVITE A FRIEND",
    title: "Fill the empty festival place",
    detail: "Choose Betty, Ms. Maple, or Coco, then invite them in your own English. A festival shines brighter when everyone belongs.",
    example: `${state.selectedInvitee}, would you like to come to the festival?`,
    actionLabel: "TRY SAYING",
    progress: "Invitation needed",
    steps: ["1 · Choose a friend", "2 · Say the invitation"],
    targetLocation: "town",
  };

  return {
    kind: "speak",
    icon: "🏮",
    eyebrow: "STORY STEP 5 OF 5 · WAKE THE LANTERN",
    title: "Give the town its final plan",
    detail: "Bring every choice together. Tell the town what happens first and what happens next, using First and then.",
    example: `First put up the ${state.flag.color} flag, then bring the fireflies to the lantern.`,
    actionLabel: "TRY SAYING",
    progress: "Final instruction needed",
    steps: ["1 · Start with First…", "2 · Add then…"],
    targetLocation: "town",
  };
}

export function moonlightPrompt(state) {
  if (state.phase === "bridge") return "Step out of the storybook when you are ready.";
  if (state.phase === "celebration") return "Stay at the festival, revisit a place, or open your moonlight memory.";
  if (state.phase === "finale" && state.location !== "town") return "Return to Town Square with all three magics.";
  if (state.location === "bakery") return state.completedTasks.has("bakery") ? "The treats will appear on the festival table." : `Ask Betty for ${state.treats.quantity} ${state.treats.food}${state.treats.quantity > 1 ? "s" : ""}, please.`;
  if (state.location === "school") return state.completedTasks.has("school") ? "Your design will hang in Town Square." : `Describe your ${state.flag.color} flag with its ${state.flag.shape}.`;
  if (state.location === "park") {
    if (state.completedTasks.has("park")) return "The fireflies are ready to follow you.";
    if (state.fireflies.size < 3) return `Find ${3 - state.fireflies.size} more glowing ${state.fireflies.size === 2 ? "friend" : "friends"}.`;
    return "Give the fireflies two steps: First…, then…";
  }
  if (state.phase === "finale" && !state.invited.size) return `Invite ${state.selectedInvitee}: Would you like to come to the festival?`;
  if (state.phase === "finale") return "Tell the town how to finish: First put up the flag, then bring the fireflies.";
  const nextTask = TASKS.find((task) => !state.completedTasks.has(task));
  if (nextTask) {
    const magic = { bakery: "Kindness Magic", school: "Color Magic", park: "Light Magic" }[nextTask];
    return `Go to ${LOCATION_NAMES[nextTask]} next and restore ${magic}.`;
  }
  return "Return to Town Square with all three magics.";
}

export function localFestivalIntent(state, message) {
  const text = clean(message);
  const destinationAliases = {
    bakery: ["bakery", "面包店"], school: ["school", "学校"], park: ["park", "公园"],
    town: ["town", "square", "广场"], storyhouse: ["story house", "storyhouse", "故事屋"],
  };
  const destination = Object.entries(destinationAliases).find(([, aliases]) => includesAny(text, aliases))?.[0];
  if (destination && includesAny(text, ["go", "visit", "back", "去", "前往", "回到"])) return { intent: "travel", destination };
  const hasKindRequest = includesAny(text, ["please", "can i have", "could i have", "may i have", "would like", "i'd like", "give me", "想要", "请给"]);
  if (state.location === "bakery" && hasKindRequest) {
    return { intent: "order_treats", food: picked(text, FOODS, state.treats.food), quantity: numberFromText(text) };
  }
  const hasColor = includesAny(text, COLORS);
  const hasShape = includesAny(text, SHAPES);
  if (state.location === "school" && (includesAny(text, ["flag", "旗"]) || (hasColor && hasShape))) {
    return { intent: "design_flag", color: picked(text, COLORS, state.flag.color), shape: picked(text, SHAPES, state.flag.shape) };
  }
  const hasEnglishSequence = text.includes("first") && text.includes("then");
  const hasChineseSequence = includesAny(text, ["先", "首先"]) && includesAny(text, ["然后", "再"]);
  if (state.location === "park" && (hasEnglishSequence || hasChineseSequence)) return { intent: "guide_fireflies" };
  if (state.location === "park" && includesAny(text, ["behind", "under", "next to", "beside", "后面", "下面", "旁边"])) return { intent: "locate_firefly" };
  if (state.location === "town" && state.phase === "finale" && includesAny(text, ["invite", "would you like", "come to", "join us", "邀请", "一起来", "参加节日"])) return { intent: "invite_friend", invitee: state.selectedInvitee };
  if (state.location === "town" && state.phase === "finale" && (hasEnglishSequence || hasChineseSequence)) return { intent: "light_lantern" };
  return { intent: includesAny(text, ["hello", "hi", "你好"]) ? "greet" : "chat" };
}

export function applyFestivalResult(state, result, message = "", source = "text") {
  const intent = result?.intent ?? "chat";
  let changed = false;
  if (intent === "travel") changed = visitMoonlightLocation(state, result.destination);
  if (intent === "order_treats" && state.location === "bakery") {
    selectTreat(state, result.food ?? state.treats.food, result.quantity ?? state.treats.quantity);
    changed = completeTask(state, "bakery") || changed;
    addEvidence(state, "kind-request", `request:${state.treats.quantity}-${state.treats.food}`, message, source);
  }
  if (intent === "design_flag" && state.location === "school") {
    selectFlagPart(state, "color", result.color ?? state.flag.color);
    selectFlagPart(state, "shape", result.shape ?? state.flag.shape);
    state.flag.described = true;
    changed = completeTask(state, "school") || changed;
    addEvidence(state, "festival-design", `design:${state.flag.color}-${state.flag.shape}`, message, source);
  }
  if (intent === "locate_firefly" && state.location === "park") {
    addEvidence(state, "light-guide", "guide:position", message, source);
    changed = true;
  }
  if (intent === "guide_fireflies" && state.location === "park" && state.fireflies.size >= 3) {
    changed = completeTask(state, "park") || changed;
    addEvidence(state, "light-guide", "guide:sequence", message, source);
  }
  if (intent === "invite_friend" && state.location === "town" && state.phase === "finale") {
    const invitee = INVITEES.includes(result.invitee) ? result.invitee : state.selectedInvitee;
    state.invited.add(invitee);
    addEvidence(state, "festival-voice", `invite:${invitee.toLowerCase().replace(/\s/g, "-")}`, message, source);
    changed = true;
  }
  if (intent === "light_lantern" && state.location === "town" && state.phase === "finale" && festivalProgress(state).readyForFinale && state.invited.size) {
    state.phase = "celebration";
    state.time = "moonlight";
    state.finalInstruction = String(message).trim();
    state.stars += 4;
    addEvidence(state, "festival-voice", "light:moon-lantern", message, source);
    changed = true;
  }
  addEnglishTurn(state, message, source, intent);
  state.lastResult = { ...result, intent, changed };
  if (result?.reply) state.guide = { speaker: result.speaker ?? "Milo", reply: result.reply, hint: result.hint || moonlightPrompt(state) };
  else state.guide.hint = moonlightPrompt(state);
  return { intent, changed };
}

export { COLORS as FESTIVAL_COLORS, FOODS as FESTIVAL_FOODS, INVITEES as FESTIVAL_INVITEES, LOCATION_NAMES as MOONLIGHT_LOCATIONS, SHAPES as FESTIVAL_SHAPES };
