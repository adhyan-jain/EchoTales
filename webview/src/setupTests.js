// react-router v7 uses TextEncoder/TextDecoder at import time; CRA's jsdom
// test environment does not provide them, so every suite that touches the
// router failed with "TextEncoder is not defined" (2026-09-26 redesign).
import { TextDecoder, TextEncoder } from 'util';

if (typeof global.TextEncoder === 'undefined') global.TextEncoder = TextEncoder;
if (typeof global.TextDecoder === 'undefined') global.TextDecoder = TextDecoder;
