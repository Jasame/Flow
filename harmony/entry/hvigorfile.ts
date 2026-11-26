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

// The site and the 内测/正式 switch (BuildProfile.FLOW_*, common/Site.ets) come from each product in
// ../build-profile.json5 only. Fields set in this module's build-profile.json5 win over every product's: the 1.0.0
// 正式版 package (1000001) opened the 内测版 that way. So none here, ever.
if (fs.readFileSync(path.resolve(__dirname, 'build-profile.json5'), 'utf-8').indexOf('"buildProfileFields"') >= 0) {
  throw new Error('harmony/entry/build-profile.json5 must not set buildProfileFields: set FLOW_* per product in ' +
    'harmony/build-profile.json5');
}

export default {
  system: hapTasks,
  plugins: []
}
