const fs = require('fs');
let file = fs.readFileSync('/Users/mac/workspace/trip-planer-agent/frotend/src/pages/WorkspacePage.vue', 'utf8');

file = file.replace(/planner\.isRunning\.value/g, 'isRunning.value');
file = file.replace(/planner\.clarificationQuestions/g, 'clarificationQuestions');

// destructure at top: `const planner = usePlanner();` to `const { state, isRunning, clarificationQuestions, initialize, updateComposer, sendMessage, toggleForm, resetConversation, submitForm, resetForm, setFlash } = usePlanner();`
// we can just replace `const planner = usePlanner();` with `const planner = usePlanner();\nconst { isRunning, clarificationQuestions } = planner;`
file = file.replace('const planner = usePlanner();', 'const planner = usePlanner();\nconst { isRunning, clarificationQuestions } = planner;');

fs.writeFileSync('/Users/mac/workspace/trip-planer-agent/frotend/src/pages/WorkspacePage.vue', file);
