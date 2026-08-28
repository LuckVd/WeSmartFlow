export const moonlightFestivalChallenges = {
  "bakery-kindness": {
    icon: "🥐", label: "Optional Easter egg challenge", title: "A treat to share",
    intro: "Help Betty practise the kind words that made the sharing basket glow.", reward: "Kindness Secret",
    words: [
      { word: "please", meaning: "a kind request word", example: "Two cookies, please." },
      { word: "two", meaning: "the number 2", example: "Can I have two cookies?" },
    ],
    questions: [
      { type: "choice", prompt: "Which request sounds kind?", sentence: "Betty is listening.", options: ["Give me cookies.", "Can I have two cookies, please?", "Cookies now."], answers: ["Can I have two cookies, please?"], hint: "Look for the request that says please." },
      { type: "fill", prompt: "Complete Betty's kind request.", sentence: "Can I have two ___, please?", placeholder: "Type the missing word", answers: ["cookies", "cakes", "breads"], hint: "Choose a treat from the bakery." },
      { type: "dialogue", prompt: "Order a festival treat in your own words.", sentence: "What would you like to share?", placeholder: "Can I have…", speaker: "Betty", npcLine: "What can I pack for the festival?", requiredGroups: [["please"], ["cookie", "cake", "bread", "treat"]], sampleAnswer: "Can I have two cookies, please?", hint: "Name a treat and add please." },
    ],
  },
  "school-colors": {
    icon: "🎨", label: "Optional Easter egg challenge", title: "Design a moon flag",
    intro: "Help Ms. Maple check the color and position words on your festival flag.", reward: "Color Secret",
    words: [
      { word: "yellow", meaning: "a warm light color", example: "The star is yellow." },
      { word: "on", meaning: "touching the top of something", example: "The star is on the flag." },
    ],
    questions: [
      { type: "choice", prompt: "Which shape belongs on a moon flag?", sentence: "Choose one shape.", options: ["star", "cookie", "tree"], answers: ["star"], hint: "It shines in the night sky." },
      { type: "fill", prompt: "Complete the position sentence.", sentence: "Put the yellow star ___ the blue flag.", placeholder: "Type the position word", answers: ["on"], hint: "The star touches the flag's surface." },
      { type: "description", prompt: "Describe your flag with a color and a shape.", sentence: "What does your flag look like?", placeholder: "My flag is…", requiredGroups: [["flag"], ["blue", "yellow", "purple"], ["star", "moon", "circle"]], sampleAnswer: "My flag is blue with a yellow star.", hint: "Say flag, one color, and one shape." },
    ],
  },
  "park-fireflies": {
    icon: "✨", label: "Optional Easter egg challenge", title: "Guide the fireflies",
    intro: "Coco wants to remember the position and sequence words that guided the lights.", reward: "Firefly Secret",
    words: [
      { word: "behind", meaning: "at the back of something", example: "Behind the tree." },
      { word: "then", meaning: "what happens next", example: "First fly up, then turn." },
    ],
    questions: [
      { type: "choice", prompt: "Where is the firefly? It is hiding at the back of the tree.", sentence: "The firefly is…", options: ["behind the tree", "on the moon", "in the bakery"], answers: ["behind the tree"], hint: "At the back means behind." },
      { type: "fill", prompt: "Complete the two-step direction.", sentence: "First fly to the fountain, ___ go to the lantern.", placeholder: "Type the sequence word", answers: ["then"], hint: "This word tells what happens next." },
      { type: "dialogue", prompt: "Give the fireflies two simple directions.", sentence: "How should the lights reach the lantern?", placeholder: "First…, then…", speaker: "Coco", npcLine: "Can you show the fireflies the way?", requiredGroups: [["first"], ["then"], ["fly", "go", "move", "come"]], sampleAnswer: "First fly to the fountain, then go to the lantern.", hint: "Use first, then, and an action word." },
    ],
  },
  "festival-memory": {
    icon: "🌙", label: "Optional Easter egg challenge", title: "My moonlight memory",
    intro: "Remember how your words brought the whole town together.", reward: "Festival Voice",
    words: [
      { word: "invite", meaning: "ask someone to join", example: "I invite Coco." },
      { word: "first", meaning: "the action that begins", example: "First put up the flag." },
    ],
    questions: [
      { type: "fill", prompt: "Complete the invitation.", sentence: "Would you like to ___ to the festival?", placeholder: "Type the missing word", answers: ["come"], hint: "This action means join us." },
      { type: "dialogue", prompt: "Invite a friend to the festival.", sentence: "What will you say?", placeholder: "Would you like…", requiredGroups: [["festival"], ["come", "join", "invite"]], sampleAnswer: "Would you like to come to the festival?", hint: "Mention the festival and ask them to come." },
      { type: "description", prompt: "Tell us what you made for the festival.", sentence: "What did you prepare?", placeholder: "I made…", requiredGroups: [["i"], ["flag", "cookie", "cake", "bread", "firefly", "light"]], sampleAnswer: "I made a flag for the festival.", hint: "Start with I and name one thing you prepared." },
    ],
  },
};
