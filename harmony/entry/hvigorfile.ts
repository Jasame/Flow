import { hapTasks } from '@ohos/hvigor-ohos-plugin';
import * as fs from 'fs';
import * as path from 'path';

// The wrapper the apps share (native/flowapp.js, docs/native-bridge.md §2) goes into rawfile as it is, every build:
// flowapp-harmony.js (the transport) comes first, this file right after it. The copy is not in git (.gitignore).
const shared = path.resolve(__dirname, '../../native/flowapp.js');
fs.copyFileSync(shared, path.resolve(__dirname, 'src/main/resources/rawfile/flowapp.js'));

export default {
  system: hapTasks,
  plugins: []
}
