# Story packages

`missing-puppy.js` is the reference package. A story package owns content; the runtime owns presentation and interaction mechanics.

`moonlight-festival.js` is the continuous-course example. It shows how a later lesson can use a new runtime, retain safe memory from a previous lesson, and still share the registry, speech layer, constrained Agent pattern, and package validation.

## Package layout

```text
stories/
├── index.js                         # register packages here
├── missing-puppy.js                 # package manifest and story content
├── missing-puppy/
    ├── challenges.js                # story-owned questions and dialogue
    └── rewards.js                   # effects earned from those challenges
├── moonlight-festival.js            # Lesson 2 manifest and learning outcomes
└── moonlight-festival/
    ├── challenges.js                # Lesson 2 optional review content
    └── rewards.js                   # Lesson 2 reward adapter
```

Every manifest is created with `defineStory()` and declares:

- `id`, `version`, `runtime`, `title`, `author`, and `description`
- `cast` and `world`
- optional declarative `world.sceneUnlocks` rules for staged place access
- optional `course.rating.hiddenChallengeIds` or `course.rating.hiddenChallengeCount` for the shared one-to-three-star course reward
- `progression` star and participation targets
- `vocabulary` and `writing.scenes`
- optional child-facing `learning.outcomes`, plus `learning.challenges` and `learning.applyReward`
- optional `learning.challengeUnlocks` rules so practice cannot appear before its story context
- a short `agent.premise`

The contract is validated as soon as the module loads. Invalid IDs, missing writing scenes, empty question sets, unsupported question types, and missing reward handlers fail early during development.

Each `learning.outcomes` entry describes one visible English power with an `id`, `icon`, `title`, child-facing `canDo` sentence, review prompt, and one or more evidence criteria. Criteria count evidence prefixes such as guided world actions and independent learner speech separately. Set `progression.starsGateMainStory: false` when demonstrated skills and story evidence should advance the plot while Adventure Stars remain optional surprise currency.

## Add another Magic Town story

1. Copy `missing-puppy.js` and the `missing-puppy/` directory.
2. Give the package a unique kebab-case `id` and reset its content, challenges, rewards, vocabulary, and writing scenes.
3. Keep `runtime: "magic-town-v1"` when the new story uses the same Town/Pet Shop/Bakery/School/Park/Story House interaction grammar and the same meet → search → care → story archetype.
4. Configure `world.sceneUnlocks` and `learning.challengeUnlocks`; `core/scene-unlocks.js` then protects navigation, Agent actions, restored progress, and challenge rewards with the same rules.
5. Configure `course.rating`, then reuse `getCourseStarsForLesson()`, `getCourseStarHint()`, and `renderCourseStars()` from `core/course-stars.js` in any completion surface.
6. Add the package to the array in `stories/index.js`.
7. Open `?story=your-story-id`.

For a story with a completely different world or interaction grammar, create a new runtime module and register it in `src/runtimes/index.js`. This keeps custom rendering and commands out of shared story content.

## Separation rule

- Story-specific nouns, dialogue, questions, rewards, and writing prompts belong in the story package.
- Reusable grading, speech, registry, and browser behavior belong in `core/` or `story-kit/`.
- Scene rendering and command orchestration belong in a versioned runtime.

When a second story needs a new capability, prefer adding a small runtime hook or generic engine API instead of checking its story ID inside shared code.
