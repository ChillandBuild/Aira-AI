"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, InterviewDraft, InterviewQuestion, VerticalStarter } from "@/lib/api";

function NameStep({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await api.onboarding.create(name.trim());
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create workspace");
      setLoading(false);
    }
  }

  return (
    <div className="card rounded-3xl p-8">
      <h1 className="font-display text-xl font-bold text-ink mb-1">Welcome to Aira AI</h1>
      <p className="font-body text-sm text-ink-muted mb-6">
        Enter your business name to set up your workspace.
      </p>

      {error && (
        <div className="mb-4 p-3 rounded-xl bg-red-50 text-red-700 font-body text-sm">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="font-body text-sm font-medium text-ink mb-1.5 block">
            Business / Organisation Name
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            className="input"
            placeholder="e.g. Sunrise University"
          />
        </div>
        <button
          type="submit"
          disabled={loading || !name.trim()}
          className="btn-primary w-full justify-center"
        >
          {loading ? "Creating…" : "Create Workspace"}
        </button>
      </form>
    </div>
  );
}

function StarterStep({ onDone, onWantInterview }: { onDone: () => void; onWantInterview: () => void }) {
  const [starters, setStarters] = useState<VerticalStarter[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [applyingKey, setApplyingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.onboarding
      .starters()
      .then((res) => setStarters(res.data))
      .catch(() => setError("Could not load starting points — you can set these up later in Settings."))
      .finally(() => setLoadingList(false));
  }, []);

  async function handlePick(key: string) {
    setApplyingKey(key);
    setError(null);
    try {
      await api.onboarding.applyStarter(key);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to apply starter");
      setApplyingKey(null);
    }
  }

  return (
    <div className="card rounded-3xl p-8">
      <h1 className="font-display text-xl font-bold text-ink mb-1">What kind of business is this?</h1>
      <p className="font-body text-sm text-ink-muted mb-6">
        Pick the closest match and Aira starts with a ready-made prompt and business
        description — you can edit everything later in Settings.
      </p>

      {error && (
        <div className="mb-4 p-3 rounded-xl bg-red-50 text-red-700 font-body text-sm">
          {error}
        </div>
      )}

      {loadingList ? (
        <div className="space-y-2">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-12 rounded-xl bg-border-subtle animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          {starters.map((s) => (
            <button
              key={s.key}
              type="button"
              onClick={() => handlePick(s.key)}
              disabled={applyingKey !== null}
              className="w-full text-left rounded-xl border border-border px-4 py-3 font-body text-sm font-medium text-ink hover:border-primary hover:bg-primary/5 disabled:opacity-50 transition-colors"
            >
              {applyingKey === s.key ? `Setting up ${s.label}…` : s.label}
            </button>
          ))}
        </div>
      )}

      <button
        type="button"
        onClick={onWantInterview}
        disabled={applyingKey !== null}
        className="w-full mt-3 font-body text-xs font-medium text-primary hover:underline disabled:opacity-50"
      >
        Or answer a few questions and let the AI write it for you
      </button>

      <button
        type="button"
        onClick={onDone}
        disabled={applyingKey !== null}
        className="w-full mt-2 font-body text-xs text-ink-muted hover:text-ink disabled:opacity-50"
      >
        Skip — I'll set this up myself
      </button>
    </div>
  );
}

function InterviewQuestionsForm({
  onDrafted,
  onCancel,
}: {
  onDrafted: (draft: InterviewDraft) => void;
  onCancel: () => void;
}) {
  const [questions, setQuestions] = useState<InterviewQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [loadingList, setLoadingList] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.onboarding
      .interviewQuestions()
      .then((res) => setQuestions(res.data))
      .catch(() => setError("Could not load the interview questions."))
      .finally(() => setLoadingList(false));
  }, []);

  const hasAnyAnswer = Object.values(answers).some((a) => a.trim());

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!hasAnyAnswer) return;
    setSubmitting(true);
    setError(null);
    try {
      const draft = await api.onboarding.interviewDraft(
        questions.map((q) => ({ question_id: q.id, answer: answers[q.id] || "" }))
      );
      onDrafted(draft);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to draft your setup");
      setSubmitting(false);
    }
  }

  return (
    <div className="card rounded-3xl p-8">
      <h1 className="font-display text-xl font-bold text-ink mb-1">A few quick questions</h1>
      <p className="font-body text-sm text-ink-muted mb-6">
        Aira's AI will write your setup from your answers. You'll review it before anything is saved.
      </p>

      {error && (
        <div className="mb-4 p-3 rounded-xl bg-red-50 text-red-700 font-body text-sm">
          {error}
        </div>
      )}

      {loadingList ? (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-16 rounded-xl bg-border-subtle animate-pulse" />
          ))}
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          {questions.map((q) => (
            <div key={q.id}>
              <label className="font-body text-sm font-medium text-ink mb-1.5 block">{q.question}</label>
              <textarea
                value={answers[q.id] || ""}
                onChange={(e) => setAnswers((prev) => ({ ...prev, [q.id]: e.target.value }))}
                rows={2}
                className="input w-full"
                placeholder="Type your answer…"
              />
            </div>
          ))}
          <button
            type="submit"
            disabled={submitting || !hasAnyAnswer}
            className="btn-primary w-full justify-center"
          >
            {submitting ? "Writing your setup…" : "Draft my setup"}
          </button>
        </form>
      )}

      <button
        type="button"
        onClick={onCancel}
        disabled={submitting}
        className="w-full mt-4 font-body text-xs text-ink-muted hover:text-ink disabled:opacity-50"
      >
        Back
      </button>
    </div>
  );
}

function InterviewReview({
  draft,
  onDone,
  onBack,
}: {
  draft: InterviewDraft;
  onDone: () => void;
  onBack: () => void;
}) {
  const [masterPrompt, setMasterPrompt] = useState(draft.master_prompt);
  const [businessDescription, setBusinessDescription] = useState(draft.business_description);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleApply() {
    setApplying(true);
    setError(null);
    try {
      await api.onboarding.interviewApply({
        master_prompt: masterPrompt.trim(),
        business_description: businessDescription.trim(),
      });
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save your setup");
      setApplying(false);
    }
  }

  return (
    <div className="card rounded-3xl p-8">
      <h1 className="font-display text-xl font-bold text-ink mb-1">Here's what the AI wrote</h1>
      <p className="font-body text-sm text-ink-muted mb-6">
        Edit anything before saving — nothing is live yet.
      </p>

      {error && (
        <div className="mb-4 p-3 rounded-xl bg-red-50 text-red-700 font-body text-sm">
          {error}
        </div>
      )}

      <div className="space-y-4">
        <div>
          <label className="font-body text-sm font-medium text-ink mb-1.5 block">
            How the AI should behave
          </label>
          <textarea
            value={masterPrompt}
            onChange={(e) => setMasterPrompt(e.target.value)}
            rows={5}
            className="input w-full"
          />
        </div>
        <div>
          <label className="font-body text-sm font-medium text-ink mb-1.5 block">
            Business description
          </label>
          <textarea
            value={businessDescription}
            onChange={(e) => setBusinessDescription(e.target.value)}
            rows={6}
            className="input w-full"
          />
        </div>
        <button
          type="button"
          onClick={handleApply}
          disabled={applying || !masterPrompt.trim() || !businessDescription.trim()}
          className="btn-primary w-full justify-center"
        >
          {applying ? "Saving…" : "Save and continue"}
        </button>
      </div>

      <button
        type="button"
        onClick={onBack}
        disabled={applying}
        className="w-full mt-4 font-body text-xs text-ink-muted hover:text-ink disabled:opacity-50"
      >
        Back to questions
      </button>
    </div>
  );
}

type Step = "name" | "starter" | "interview_questions" | "interview_review";

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("name");
  const [draft, setDraft] = useState<InterviewDraft | null>(null);

  function finish() {
    router.push("/dashboard");
    router.refresh();
  }

  const isWideStep = step === "interview_questions" || step === "interview_review";

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className={isWideStep ? "w-full max-w-lg" : "w-full max-w-sm"}>
        {step === "name" && <NameStep onCreated={() => setStep("starter")} />}
        {step === "starter" && (
          <StarterStep onDone={finish} onWantInterview={() => setStep("interview_questions")} />
        )}
        {step === "interview_questions" && (
          <InterviewQuestionsForm
            onDrafted={(d) => {
              setDraft(d);
              setStep("interview_review");
            }}
            onCancel={() => setStep("starter")}
          />
        )}
        {step === "interview_review" && draft && (
          <InterviewReview draft={draft} onDone={finish} onBack={() => setStep("interview_questions")} />
        )}
      </div>
    </div>
  );
}
