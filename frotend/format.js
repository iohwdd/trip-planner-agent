import fs from 'fs';

let content = fs.readFileSync('src/pages/WorkspacePage.vue', 'utf-8');

// In the template, replace isRunning.value with isRunning
// The template starts at <template>
const parts = content.split('<template>');
if (parts.length > 1) {
    parts[1] = parts[1].replace(/isRunning\.value/g, 'isRunning');
    parts[1] = parts[1].replace(/clarificationQuestions\.value/g, 'clarificationQuestions');
}
fs.writeFileSync('src/pages/WorkspacePage.vue', parts.join('<template>'));
