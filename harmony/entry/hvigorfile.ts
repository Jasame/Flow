import { hapTasks } from '@ohos/hvigor-ohos-plugin';
import { execFileSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

const rawfile = path.resolve(__dirname, 'src/main/resources/rawfile');

// The wrapper the apps share (native/flowapp.js, docs/native-bridge.md §2) goes into rawfile as it is, every build:
// flowapp-harmony.js (the transport) comes first, this file right after it. The copy is not in git (.gitignore).
fs.copyFileSync(path.resolve(__dirname, '../../native/flowapp.js'), path.join(rawfile, 'flowapp.js'));

// 《用户协议》 and 《隐私和数据》 for the question on the first start (common/Consent.ets), made from the site's own guide
// by the script Android uses (android/tools/legal_docs.py → rawfile/legal/legal.json): nothing is opened on the
// network before the learner answers, and the words are the site's. Not in git either.
execFileSync('python3', [path.resolve(__dirname, '../../android/tools/legal_docs.py'), rawfile], { stdio: 'inherit' });

export default {
  system: hapTasks,
  plugins: []
}
