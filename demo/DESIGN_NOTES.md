# Design notes for the demo page

Reference pass on 21 Nov 2026. I took headless Chrome screenshots at 1440 px of the galleries
(godly.website, saaspo.com, land-book.com, lapa.ninja, awwwards.com, siteinspire.com, dark.design)
and of real sites in voice AI and realtime audio: ElevenLabs, Cartesia, Vapi, Retell, LiveKit,
Deepgram, Hume, Sesame, Krisp, AssemblyAI, Speechmatics, Resemble, Suno and Flam (flamapp.ai).
The north star did not have to come from voice AI. It only had to suit this content.

## Finalists

1. **Suno (suno.com).** Dark, warm, grainy gradient atmosphere. A tight grotesk headline
   (Neue Montreal) with an editorial serif (Editorial New) for section heads, and one big
   interactive object in the middle of the hero.
2. **Cartesia (cartesia.ai).** White canvas, a serif display (PP Kyoto) over a quiet grotesk
   (ABC Diatype), generous whitespace and thin vertical rails. Very calm and very credible.
3. **AssemblyAI (assemblyai.com).** A big serif display (Oceanic Text) and a product demo framed
   right under the headline. Strong, but it leans on all-caps mono labels throughout.

## Pick: Suno

This page has one job: make a few seconds of audio visible. Suno's hero treats sound as a lit
object sitting in a warm, textured dark space, and that is the right stage for a waveform replay.
Its palette of umber, ember and grain is also close to Flam's own hero (a blurred orange and teal
landscape). That keeps the page in the target company's world without copying its brand.

What I take from it:

- **Atmosphere, not decoration.** A warm umber field with soft radial light and a fine grain
  overlay sits behind the hero only. The rest of the page is plain dark, so the light points at the
  timeline.
- **Two clearly different faces.** A tight grotesk for the headline and body (General Sans,
  the closest free face to Neue Montreal) and a high-contrast editorial serif for section heads
  (Instrument Serif, close to Editorial New). Mono (Geist Mono) appears only inside code.
- **One object in the hero.** Suno centres its prompt box. Here the centre is the interruption
  replay itself: three lanes, a playhead, and one lane that keeps talking while the other goes quiet.
- **Rounded only where you can touch.** Pills for the speed toggle and Replay, soft corners on the
  code block, and nothing else is boxed. Sections are separated by space and hairlines, not cards.
- **Big type, short lines.** The headline is set large with negative tracking. Body copy stays
  under about 60 characters per line, with muted warm grey for secondary text.

## Tokens

| Token  | Hex       | Role                                                 |
|--------|-----------|------------------------------------------------------|
| night  | `#17110F` | page ground (warm umber, not a neutral near-black)   |
| bone   | `#F2ECE4` | text and agent speech before the interrupt           |
| dust   | `#A5988D` | secondary text, axis                                 |
| ember  | `#FF5B3A` | README pattern still talking after `cancel()`        |
| tide   | `#86E0C9` | the wrapper going quiet                              |
| sand   | `#E8B86A` | the user's voice                                     |
