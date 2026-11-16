// Synthetic runtime regression only. Not the deployed entry point.
import worker from "./worker.mjs";
import sealedbox from "tweetnacl-sealedbox-js";
export { OneTimeState } from "./worker.mjs";
export default {
  async fetch(request, env) {
    if (new URL(request.url).pathname !== "/zz-seal")
      return worker.fetch(request, env);
    const { publicKey } = await request.json();
    const key = Uint8Array.from(atob(publicKey), (c) => c.charCodeAt(0));
    const cipher = sealedbox.seal(new TextEncoder().encode("ZZSYNTHETIC"), key);
    return new Response(btoa(String.fromCharCode(...cipher)));
  },
};
