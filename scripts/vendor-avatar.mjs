import { copyFile, mkdir } from 'node:fs/promises';

await mkdir('frontend/vendor', {recursive:true});
await copyFile('node_modules/pixi.js/dist/browser/pixi.min.js','frontend/vendor/pixi.min.js');
await copyFile('node_modules/pixi-live2d-display/dist/cubism4.min.js','frontend/vendor/cubism4.min.js');
await copyFile('node_modules/pixi.js/LICENSE','frontend/vendor/PIXI-LICENSE.txt');
await copyFile('node_modules/pixi-live2d-display/LICENSE','frontend/vendor/LIVE2D-DISPLAY-LICENSE.txt');
