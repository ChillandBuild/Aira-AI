/*
  Install snippets for the anril-connector plug-in. They follow sdk/python/README.md
  and sdk/node/README.md: the package is anril-connector, and anril_public_key /
  anrilPublicKey is required (it is the key shown above the snippets).
*/

export type Language = "python" | "node";

export interface Snippet {
  title: string;
  code: string;
}

const KEY_PLACEHOLDER = "<paste the Anril public key from above>";

function python(publicKey: string): Snippet[] {
  return [
    {
      title: "1. Install",
      code: `pip install anril-connector`,
    },
    {
      title: "2. Connect, then tell Anril about each event",
      code: `import os
from anril_connector import AnrilPrivateSend

ps = AnrilPrivateSend(
    license_key=os.environ["ANRIL_LICENSE_KEY"],   # the key you created above
    meta_token=os.environ["META_TOKEN"],           # your own WhatsApp Cloud API token
    phone_number_id=os.environ["META_PHONE_NUMBER_ID"],
    anril_public_key="${publicKey}",
)

# when a customer buys:
result = ps.track("purchased", "98765 43210", name="Asha Rao", extra={"order_id": "A42"})
print(result.status, result.reason)   # sent | queued | skipped | failed`,
    },
    {
      title: "3. Every minute (cron)",
      code: `* * * * * cd /srv/app && python -c "from myapp import ps; ps.run_due(); ps.report_usage()"`,
    },
  ];
}

function node(publicKey: string): Snippet[] {
  return [
    {
      title: "1. Install",
      code: `npm install anril-connector`,
    },
    {
      title: "2. Connect, then tell Anril about each event",
      code: `import { AnrilPrivateSend } from "anril-connector";

export const anril = new AnrilPrivateSend({
  licenseKey: process.env.ANRIL_LICENSE_KEY!,    // the key you created above
  anrilPublicKey: "${publicKey}",
  metaToken: process.env.META_TOKEN!,            // your own WhatsApp Cloud API token
  phoneNumberId: process.env.META_PHONE_NUMBER_ID!,
  store: "sqlite:./anril_connector.db",
});

// when a customer buys:
const result = await anril.track("purchased", { phone: "+919876543221", name: "Ravi" });
// result.status is one of: sent, queued, skipped, failed (result.reason says why)`,
    },
    {
      title: "3. Every minute (cron or a worker)",
      code: `// worker.mjs, started by cron: * * * * * cd /srv/app && node worker.mjs
import { anril } from "./anril.js";

await anril.runDue();       // sends messages whose rule has a delay
await anril.reportUsage();  // sends today's counts to Anril (throttled to every 15 min)
await anril.close();`,
    },
  ];
}

export function snippetsFor(language: Language, publicKey: string | null): Snippet[] {
  const key = publicKey ?? KEY_PLACEHOLDER;
  return language === "python" ? python(key) : node(key);
}
