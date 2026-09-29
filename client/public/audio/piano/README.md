# Piano samples

The app's piano (Listen mode, the other hand in one-hand practice, concept lessons) plays these
samples: the **Salamander Grand Piano** by Alexander Holm (a Yamaha C5), licensed
[CC BY 3.0](http://creativecommons.org/licenses/by/3.0/). These are the Tone.js MP3 exports
(`https://tonejs.github.io/audio/salamander/`): one velocity layer, one sample every minor third
from A0 to C8. The app plays each note from the nearest sample, re-pitched by at most a semitone
and a half (`client/src/lib/audio.ts`).

They are kept in the repository (about 2 MB) so every deploy serves them from the piano server
and the app keeps working without internet.
