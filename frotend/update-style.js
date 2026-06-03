import fs from 'fs';
let style = fs.readFileSync('src/style.css', 'utf-8');

style = style.replace(
  /\.chat-panel \{\s*min-height: 0;\s*height: 100%;\s*display: grid;\s*grid-template-rows:[^;]+;\s*gap:[^;]+;/g,
  `.chat-panel {\n  min-height: 0;\n  height: 100%;\n  display: flex;\n  flex-direction: column;\n  gap: 18px;`
);

fs.writeFileSync('src/style.css', style);
