// Private stdin to sealed stdout, consumed only by the Python parent process.
import sealedbox from 'tweetnacl-sealedbox-js';
const chunks = [];
let length = 0;
for await (const chunk of process.stdin) {
  length += chunk.length;
  if (length > 100000) process.exit(1);
  chunks.push(chunk);
}
const raw = Buffer.concat(chunks).toString('utf8');
try {
  const value = JSON.parse(raw);
  const cipher = sealedbox.seal(new TextEncoder().encode(value.value), new Uint8Array(Buffer.from(value.public, 'base64')));
  process.stdout.write(Buffer.from(cipher).toString('base64'));
} catch {
  process.exitCode = 1;
}
