"use client";

import Link from "next/link";
import { Compass } from "lucide-react";
import { DevSection } from "./DevSection";

interface Door {
  name: string;
  how: string;
  seesNumbers: boolean;
  href: string | null;
  linkLabel: string;
}

interface DoorChooserProps {
  /** True when this account has "Send from your server" switched on. */
  sendFromServerOn: boolean;
}

function doors(sendFromServerOn: boolean): Door[] {
  return [
    {
      name: "Anril sends for you",
      how: "Your app calls one signed address with a template ID or an event (like \"Priya purchased\"), whichever this account is set to. Anril sends the message and customer replies land in Anril's inbox. Easiest to set up.",
      seesNumbers: true,
      href: "#send-template",
      linkLabel: "Send a template or event",
    },
    {
      name: "Your server sends",
      how: "A small plug-in on your own server sends the message with your own WhatsApp token. Anril never sees the numbers, only daily counts.",
      seesNumbers: false,
      href: sendFromServerOn ? "#send-from-server" : null,
      linkLabel: "Send from your server",
    },
  ];
}

export function DoorChooser({ sendFromServerOn }: DoorChooserProps) {
  const rows = doors(sendFromServerOn);
  return (
    <DevSection
      id="which-door"
      icon={Compass}
      title="Which one do I need?"
      intro="There are two ways to send WhatsApp messages from your own software. Pick by one question: who should send, and may Anril see your customers' numbers?"
    >
      <div className="overflow-x-auto rounded-2xl border border-border-subtle">
        <table className="w-full text-left text-xs">
          <thead className="bg-surface-subtle text-[11px] font-bold uppercase tracking-wider text-ink-muted">
            <tr>
              <th className="px-4 py-2.5">Way in</th>
              <th className="px-4 py-2.5">How it works</th>
              <th className="px-4 py-2.5">Anril sees numbers?</th>
              <th className="px-4 py-2.5">Go to</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {rows.map((door) => (
              <tr key={door.name} className="align-top">
                <td className="whitespace-nowrap px-4 py-3 font-semibold text-ink">{door.name}</td>
                <td className="min-w-[220px] px-4 py-3 text-ink-secondary">{door.how}</td>
                <td className="px-4 py-3">
                  <span
                    className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                      door.seesNumbers ? "bg-gray-100 text-gray-600" : "bg-emerald-50 text-emerald-700"
                    }`}
                  >
                    {door.seesNumbers ? "Yes" : "No"}
                  </span>
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  {door.href ? (
                    <a href={door.href} className="font-semibold text-primary hover:underline">
                      {door.linkLabel} &darr;
                    </a>
                  ) : (
                    <span className="text-ink-muted">Not switched on for this account</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-ink-muted">
        Not sure? Start with &ldquo;Anril sends for you&rdquo;. Choose &ldquo;Your server sends&rdquo; only if your customers&apos; numbers must never leave your own systems.
        Just want a form on your website? That is set up on the{" "}
        <Link href="/dashboard/auto-messages#get-customers-in" className="font-semibold text-primary hover:underline">
          Auto Messages page
        </Link>
        .
      </p>
    </DevSection>
  );
}
