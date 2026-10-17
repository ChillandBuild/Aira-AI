"use client";

import { useRef, useState, type FormEvent, type ReactNode } from "react";
import ui from "./site.module.css";
import { INDUSTRY_OPTIONS, submitDemo, validateDemo, type DemoErrors, type DemoFields } from "./demo-request";
import s from "./Demo.module.css";

type Status = { kind: "idle" } | { kind: "sending" } | { kind: "sent" } | { kind: "error"; message: string };

const EMPTY: DemoFields = { name: "", phone: "", company: "", industry: "" };
const ORDER: readonly (keyof DemoFields)[] = ["name", "phone", "company", "industry"];

type FieldProps = {
  id: keyof DemoFields;
  label: string;
  error?: string;
  children: (a11y: { id: string; name: string; "aria-invalid": boolean; "aria-describedby"?: string }) => ReactNode;
};

function Field({ id, label, error, children }: FieldProps) {
  const inputId = `demo-${id}`;
  const errorId = `${inputId}-err`;
  return (
    <div className={s.field}>
      <label htmlFor={inputId}>{label}</label>
      {children({ id: inputId, name: id, "aria-invalid": Boolean(error), "aria-describedby": error ? errorId : undefined })}
      {error && <p id={errorId} className={s.fieldError}>{error}</p>}
    </div>
  );
}

/** Demo request. Validates on submit, shows sending and error states, and ignores repeat submits while one is in flight. */
export function DemoForm() {
  const [fields, setFields] = useState<DemoFields>(EMPTY);
  const [errors, setErrors] = useState<DemoErrors>({});
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const inFlight = useRef(false);
  const formRef = useRef<HTMLFormElement>(null);
  const doneRef = useRef<HTMLHeadingElement>(null);

  const set = (key: keyof DemoFields) => (e: { target: { value: string } }) => {
    setFields((f) => ({ ...f, [key]: e.target.value }));
    if (errors[key]) setErrors((er) => ({ ...er, [key]: undefined }));
  };

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (inFlight.current) return;
    const found = validateDemo(fields);
    setErrors(found);
    const firstBad = ORDER.find((k) => found[k]);
    if (firstBad) {
      formRef.current?.querySelector<HTMLElement>(`#demo-${firstBad}`)?.focus();
      return;
    }
    inFlight.current = true;
    setStatus({ kind: "sending" });
    const honeypot = (formRef.current?.elements.namedItem("_hp") as HTMLInputElement | null)?.value ?? "";
    const result = await submitDemo(fields, honeypot);
    inFlight.current = false;
    if (result.ok) {
      setStatus({ kind: "sent" });
      requestAnimationFrame(() => doneRef.current?.focus());
    } else {
      setStatus({ kind: "error", message: result.message });
    }
  }

  if (status.kind === "sent") {
    return (
      <div className={s.form} role="status">
        <h3 ref={doneRef} tabIndex={-1} className={s.doneTitle}>Thank you. We have your details.</h3>
        <p className={s.doneText}>We will contact you on {fields.phone.trim()} to set up your demo.</p>
      </div>
    );
  }

  const sending = status.kind === "sending";
  return (
    <form ref={formRef} className={s.form} noValidate onSubmit={onSubmit} aria-busy={sending}>
      <Field id="name" label="Your name" error={errors.name}>
        {(a) => <input {...a} autoComplete="name" maxLength={80} value={fields.name} onChange={set("name")} />}
      </Field>
      <Field id="phone" label="Phone number" error={errors.phone}>
        {(a) => <input {...a} type="tel" inputMode="tel" autoComplete="tel" maxLength={20} value={fields.phone} onChange={set("phone")} />}
      </Field>
      <Field id="company" label="Business name" error={errors.company}>
        {(a) => <input {...a} autoComplete="organization" maxLength={120} value={fields.company} onChange={set("company")} />}
      </Field>
      <Field id="industry" label="Industry" error={errors.industry}>
        {(a) => (
          <select {...a} value={fields.industry} onChange={set("industry")}>
            <option value="">Choose one</option>
            {INDUSTRY_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        )}
      </Field>
      {/* Bots fill this; people never see it. */}
      <div className={s.hp} aria-hidden="true">
        <label htmlFor="demo-hp">Leave this empty</label>
        <input id="demo-hp" name="_hp" tabIndex={-1} autoComplete="off" />
      </div>
      <button className={ui.btn} type="submit" disabled={sending}>
        {sending ? "Sending…" : "Book a demo"}
      </button>
      <p className={s.note} role="alert">{status.kind === "error" ? status.message : ""}</p>
    </form>
  );
}
