import { validateToolArguments } from '/opt/homebrew/Cellar/pi-coding-agent/1.5.2/libexec/lib/node_modules/@earendil-works/pi-coding-agent/node_modules/@earendil-works/pi-ai/dist/utils/validation.js';
import { createBashTool } from '/opt/homebrew/Cellar/pi-coding-agent/1.5.2/libexec/lib/node_modules/@earendil-works/pi-coding-agent/dist/core/tools/bash.js';
console.log(JSON.stringify(validateToolArguments(createBashTool(process.cwd()), {name:'bash', arguments:JSON.parse(process.argv[2])})));
