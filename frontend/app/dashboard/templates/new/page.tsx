"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  Check,
  ChevronRight,
  ChevronLeft,
  AlertCircle,
  Upload,
  X,
  FileCode,
  Lock,
} from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { LANGUAGES, CATEGORIES } from "../types";
import type { Button } from "../types";
import ButtonBuilder from "../components/button-builder";
import VariableInserter from "../components/variable-inserter";
import WhatsAppPreview from "../components/whatsapp-preview";

function hasEmoji(str: string): boolean {
  const emojiRegex = /[\u2600-\u27BF]|[\uD83C-\uD83E][\uDC00-\uDFFF]/;
  return emojiRegex.test(str);
}

export default function NewTemplatePage() {
  const router = useRouter();
  const [currentStep, setCurrentStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form State
  const [name, setName] = useState("");
  const [category, setCategory] = useState<"MARKETING" | "UTILITY" | "AUTHENTICATION">("MARKETING");
  const [language, setLanguage] = useState("en");

  // Content State
  const [headerType, setHeaderType] = useState<"NONE" | "TEXT" | "IMAGE" | "VIDEO" | "DOCUMENT">("NONE");
  const [headerText, setHeaderText] = useState("");
  const [headerMediaUrl, setHeaderMediaUrl] = useState("");
  const [uploadingMedia, setUploadingMedia] = useState(false);
  const [bodyText, setBodyText] = useState("");
  const [footerText, setFooterText] = useState("");

  // Buttons State
  const [buttons, setButtons] = useState<Button[]>([]);

  const generatedName = name
    .toLowerCase()
    .replace(/[^a-z0-9\s_]/g, "")
    .trim()
    .replace(/\s+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "");

  // Media upload handler
  async function handleMediaUpload(file: File) {
    setUploadingMedia(true);
    setError(null);
    try {
      const authHeaders = await getAuthHeaders();
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch(`${API_URL}/api/v1/templates/upload-media`, {
        method: "POST",
        headers: authHeaders,
        body: formData,
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || "Failed to upload media");
      }

      const data = await res.json();
      // Meta resumable upload returns header_handle
      const handle = data.header_handle;
      setHeaderMediaUrl(handle);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Media upload failed");
    } finally {
      setUploadingMedia(false);
    }
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) {
      handleMediaUpload(file);
    }
  }

  function clearMedia() {
    setHeaderMediaUrl("");
  }

  // Next / Prev step navigation
  const nextStep = () => {
    setError(null);
    if (currentStep === 1) {
      if (!name.trim()) {
        setError("Please enter a template name.");
        return;
      }
    } else if (currentStep === 2) {
      if (!bodyText.trim()) {
        setError("Message body text cannot be empty.");
        return;
      }
      if (headerType === "TEXT" && !headerText.trim()) {
        setError("Please enter header text.");
        return;
      }
      if (headerType === "TEXT" && hasEmoji(headerText)) {
        setError("Emojis are not allowed in the header text.");
        return;
      }
      if (headerType !== "NONE" && headerType !== "TEXT" && !headerMediaUrl) {
        setError("Please upload a media file or provide a handle.");
        return;
      }
    } else if (currentStep === 3) {
      const trimmedTexts = buttons.map((b) => b.text.trim().toLowerCase()).filter(Boolean);
      const uniqueTexts = new Set(trimmedTexts);
      if (uniqueTexts.size < trimmedTexts.length) {
        setError("You can't enter the same text for multiple buttons.");
        return;
      }
    }
    setCurrentStep((prev) => Math.min(prev + 1, 4));
  };

  const prevStep = () => {
    setError(null);
    setCurrentStep((prev) => Math.max(prev - 1, 1));
  };

  // Submit template to API
  async function handleSubmit() {
    setLoading(true);
    setError(null);
    try {
      if (headerType === "TEXT" && hasEmoji(headerText)) {
        throw new Error("Emojis are not allowed in the header text.");
      }
      const trimmedTexts = buttons.map((b) => b.text.trim().toLowerCase()).filter(Boolean);
      if (new Set(trimmedTexts).size < trimmedTexts.length) {
        throw new Error("You can't enter the same text for multiple buttons.");
      }
      const authHeaders = await getAuthHeaders();
      const payload = {
        name: generatedName,
        category,
        language,
        body_text: bodyText.trim(),
        header_text: headerType === "TEXT" ? headerText.trim() : null,
        header_media_type: headerType !== "NONE" && headerType !== "TEXT" ? headerType : null,
        header_media_url: headerType !== "NONE" && headerType !== "TEXT" ? headerMediaUrl : null,
        footer_text: footerText.trim() || null,
        buttons: buttons.length > 0 ? buttons : null,
      };

      const res = await fetch(`${API_URL}/api/v1/templates/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders,
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || "Failed to submit template to WhatsApp");
      }

      router.push("/dashboard/templates");
    } catch (e) {
      setError(e instanceof Error ? e.message : "An unexpected error occurred");
    } finally {
      setLoading(false);
    }
  }

  // Quick select helper for category
  const selectCategory = (val: "MARKETING" | "UTILITY" | "AUTHENTICATION") => {
    setCategory(val);
    if (val === "AUTHENTICATION") {
      // Setup default OTP configuration
      setHeaderType("NONE");
      setBodyText("{{1}} is your verification code. For security, do not share this code.");
      setFooterText("This code expires in 10 minutes.");
      setButtons([{ type: "COPY_CODE", text: "Copy Code" }]);
    } else {
      setBodyText("");
      setFooterText("");
      setButtons([]);
    }
  };

  return (
    <div className="max-w-6xl mx-auto pb-12">
      {/* Header and Back Link */}
      <div className="mb-6">
        <Link
          href="/dashboard/templates"
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl hover:bg-[#f0ece4] text-[#1c1917]/80 hover:text-[#1c1917] font-label text-sm font-semibold transition-all border border-[#e8e3db] bg-transparent"
        >
          <ArrowLeft size={14} /> Back to Templates
        </Link>
      </div>

      {/* Stepper progress */}
      <div className="mb-8 p-5 bg-white rounded-2xl border border-border-subtle shadow-sm flex items-center justify-between">
        {[
          { step: 1, label: "Template Info" },
          { step: 2, label: "Message Content" },
          { step: 3, label: "Interactive Buttons" },
          { step: 4, label: "Review & Submit" },
        ].map((s) => (
          <div key={s.step} className="flex items-center gap-3 flex-1 last:flex-none">
            <div className="flex items-center gap-2">
              <div
                className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold transition-all ${
                  currentStep > s.step
                    ? "bg-emerald-500 text-white"
                    : currentStep === s.step
                      ? "bg-emerald-50 text-emerald-600 border border-emerald-500"
                      : "bg-surface-subtle text-ink-muted"
                }`}
              >
                {currentStep > s.step ? <Check size={14} /> : s.step}
              </div>
              <span
                className={`text-sm font-medium ${
                  currentStep === s.step ? "text-ink font-semibold" : "text-ink-muted"
                }`}
              >
                {s.label}
              </span>
            </div>
            {s.step < 4 && (
              <div className="h-[1px] bg-border-subtle flex-1 mx-4 hidden md:block" />
            )}
          </div>
        ))}
      </div>

      {error && (
        <div className="mb-6 p-4 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm flex items-start gap-2.5 animate-slide-up">
          <AlertCircle size={16} className="mt-0.5 shrink-0" />
          <p className="font-body">{error}</p>
        </div>
      )}

      {/* Main Grid: Form Left, Preview Right */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column: Config Panel */}
        <div className="lg:col-span-7 bg-white rounded-3xl border border-border-subtle p-6 shadow-sm space-y-6 min-h-[500px]">
          {/* STEP 1: TEMPLATE INFO */}
          {currentStep === 1 && (
            <div className="space-y-6 animate-fade-in">
              <h2 className="font-display text-lg font-bold text-ink border-b border-border-subtle pb-3">
                Step 1: Template Info
              </h2>

              {/* Template Title */}
              <div>
                <label className="font-body text-sm font-medium text-ink mb-1.5 block">
                  Template Title
                </label>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Spring Sale Announcement"
                  className="input"
                />
                {name.trim() && (
                  <p className="font-body text-[11px] text-ink-muted mt-2">
                    Submitted Name:{" "}
                    <span className="font-mono text-ink bg-surface-subtle px-1.5 py-0.5 rounded font-bold">
                      {generatedName}
                    </span>
                  </p>
                )}
              </div>

              {/* Categories */}
              <div>
                <label className="font-body text-sm font-medium text-ink mb-2 block">
                  Template Category
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {CATEGORIES.map((catOpt) => {
                    const isSelected = category === catOpt.value;
                    return (
                      <button
                        key={catOpt.value}
                        type="button"
                        onClick={() => selectCategory(catOpt.value)}
                        className={`p-4 text-left rounded-2xl border-2 transition-all flex flex-col justify-between h-32 ${
                          isSelected
                            ? "border-emerald-500 bg-emerald-50/50 shadow-sm"
                            : "border-border-subtle hover:border-border bg-white"
                        }`}
                      >
                        <span className="text-xl">
                          {catOpt.value === "MARKETING"
                            ? "📣"
                            : catOpt.value === "UTILITY"
                              ? "🔔"
                              : "🔐"}
                        </span>
                        <div>
                          <p className="font-body text-sm font-semibold text-ink">
                            {catOpt.label}
                          </p>
                          <p className="font-body text-[10px] text-ink-muted leading-tight mt-0.5">
                            {catOpt.description}
                          </p>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Language */}
              <div>
                <label className="font-body text-sm font-medium text-ink mb-1.5 block">
                  Language
                </label>
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  className="input"
                >
                  {LANGUAGES.map((lang) => (
                    <option key={lang.code} value={lang.code}>
                      {lang.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {/* STEP 2: MESSAGE CONTENT */}
          {currentStep === 2 && (
            <div className="space-y-6 animate-fade-in">
              <h2 className="font-display text-lg font-bold text-ink border-b border-border-subtle pb-3">
                Step 2: Message Content
              </h2>

              {/* Header */}
              {category !== "AUTHENTICATION" ? (
                <div>
                  <label className="font-body text-sm font-medium text-ink mb-1.5 block">
                    Header Type
                  </label>
                  <select
                    value={headerType}
                    onChange={(e) => {
                      setHeaderType(e.target.value as "NONE" | "TEXT" | "IMAGE" | "VIDEO" | "DOCUMENT");
                      setHeaderText("");
                      clearMedia();
                    }}
                    className="input w-full mb-3"
                  >
                    <option value="NONE">None</option>
                    <option value="TEXT">Text Header</option>
                    <option value="IMAGE">Image Header</option>
                    <option value="VIDEO">Video Header</option>
                    <option value="DOCUMENT">Document Header</option>
                  </select>

                  {headerType === "TEXT" && (
                    <input
                      value={headerText}
                      onChange={(e) => setHeaderText(e.target.value)}
                      maxLength={60}
                      placeholder="e.g. Limited Time Offer"
                      className="input"
                    />
                  )}

                  {/* Media uploads */}
                  {["IMAGE", "VIDEO", "DOCUMENT"].includes(headerType) && (
                    <div className="mt-3">
                      {headerMediaUrl ? (
                        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <FileCode size={16} className="text-emerald-600" />
                            <span className="font-body text-xs text-emerald-800 font-medium truncate max-w-xs">
                              Media file uploaded successfully
                            </span>
                          </div>
                          <button
                            type="button"
                            onClick={clearMedia}
                            className="p-1 hover:bg-emerald-100 rounded-lg text-emerald-600"
                          >
                            <X size={14} />
                          </button>
                        </div>
                      ) : (
                        <div>
                          <label className="border-2 border-dashed border-border-subtle rounded-2xl p-6 text-center cursor-pointer hover:border-emerald-500/50 hover:bg-emerald-50/50 transition-colors block relative">
                            <input
                              type="file"
                              accept={
                                headerType === "IMAGE"
                                  ? "image/jpeg,image/png,image/webp"
                                  : headerType === "VIDEO"
                                    ? "video/mp4"
                                    : ".pdf,.doc,.docx"
                              }
                              onChange={handleFileSelect}
                              className="hidden"
                            />
                            <Upload size={24} className="mx-auto text-ink-muted mb-2" />
                            <p className="font-body text-xs text-ink-secondary font-medium">
                              {uploadingMedia ? "Uploading to Meta..." : `Upload template ${headerType.toLowerCase()}`}
                            </p>
                            <p className="font-body text-[10px] text-ink-muted mt-1">
                              Max size 10MB
                            </p>
                          </label>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                <div className="p-4 bg-surface-subtle border border-border-subtle rounded-2xl flex items-start gap-2.5">
                  <Lock size={15} className="text-ink-muted shrink-0 mt-0.5" />
                  <p className="font-body text-xs text-ink-muted leading-relaxed">
                    Authentication templates enforce a <strong>NONE</strong> header type on WhatsApp.
                  </p>
                </div>
              )}

              {/* Body Text */}
              <div>
                <VariableInserter
                  label="Message Body"
                  value={bodyText}
                  onChange={setBodyText}
                  rows={6}
                  maxLength={1024}
                  placeholder="Enter template message body here..."
                />
              </div>

              {/* Footer Text */}
              {category !== "AUTHENTICATION" ? (
                <div>
                  <label className="font-body text-sm font-medium text-ink mb-1.5 block">
                    Footer Text <span className="text-ink-muted font-normal">(optional, max 60 chars)</span>
                  </label>
                  <input
                    value={footerText}
                    onChange={(e) => setFooterText(e.target.value)}
                    maxLength={60}
                    placeholder="e.g. Reply STOP to opt out"
                    className="input"
                  />
                </div>
              ) : (
                <div>
                  <label className="font-body text-sm font-medium text-ink mb-1.5 block">
                    Footer Text <span className="text-ink-muted font-normal">(optional, max 60 chars)</span>
                  </label>
                  <input
                    value={footerText}
                    onChange={(e) => setFooterText(e.target.value)}
                    maxLength={60}
                    className="input"
                  />
                </div>
              )}
            </div>
          )}

          {/* STEP 3: INTERACTIVE BUTTONS */}
          {currentStep === 3 && (
            <div className="space-y-6 animate-fade-in">
              <h2 className="font-display text-lg font-bold text-ink border-b border-border-subtle pb-3">
                Step 3: Interactive Buttons
              </h2>

              {category === "AUTHENTICATION" ? (
                <div className="space-y-4">
                  <div className="p-4 bg-emerald-50 border border-emerald-100 rounded-2xl">
                    <p className="font-body text-xs text-emerald-800 leading-relaxed">
                      OTP templates require a single action button. You can choose a <strong>Copy Code</strong> button, or a <strong>One-Tap Autofill</strong> button for Android.
                    </p>
                  </div>
                  <ButtonBuilder
                    buttons={buttons}
                    onChange={setButtons}
                    maxButtons={1}
                    disableCTA={false}
                  />
                </div>
              ) : (
                <ButtonBuilder
                  buttons={buttons}
                  onChange={setButtons}
                  maxButtons={10}
                  disableCTA={false}
                />
              )}
            </div>
          )}

          {/* STEP 4: REVIEW AND SUBMIT */}
          {currentStep === 4 && (
            <div className="space-y-6 animate-fade-in">
              <h2 className="font-display text-lg font-bold text-ink border-b border-border-subtle pb-3">
                Step 4: Review & Submit
              </h2>

              <p className="font-body text-sm text-ink-muted">
                Review your template details before submitting to WhatsApp for review. This process takes 24-72 hours.
              </p>

              <div className="grid grid-cols-2 gap-4 p-4 rounded-2xl bg-surface-subtle border border-border-subtle">
                <div>
                  <p className="font-body text-[11px] text-ink-muted uppercase font-bold tracking-wider">
                    Name
                  </p>
                  <p className="font-mono text-sm font-semibold text-ink truncate mt-0.5">
                    {generatedName}
                  </p>
                </div>
                <div>
                  <p className="font-body text-[11px] text-ink-muted uppercase font-bold tracking-wider">
                    Category
                  </p>
                  <p className="font-body text-sm font-semibold text-ink mt-0.5">
                    {category}
                  </p>
                </div>
                <div>
                  <p className="font-body text-[11px] text-ink-muted uppercase font-bold tracking-wider">
                    Language
                  </p>
                  <p className="font-body text-sm font-semibold text-ink mt-0.5">
                    {LANGUAGES.find((l) => l.code === language)?.label || language}
                  </p>
                </div>
                <div>
                  <p className="font-body text-[11px] text-ink-muted uppercase font-bold tracking-wider">
                    Header type
                  </p>
                  <p className="font-body text-sm font-semibold text-ink mt-0.5">
                    {headerType}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Stepper Buttons */}
          <div className="border-t border-border-subtle pt-6 flex items-center justify-between">
            {currentStep > 1 ? (
              <button
                type="button"
                onClick={prevStep}
                className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl border border-border-subtle hover:bg-surface-subtle font-medium text-sm text-ink transition-colors"
              >
                <ChevronLeft size={16} />
                Back
              </button>
            ) : (
              <div />
            )}

            {currentStep < 4 ? (
              <button
                type="button"
                onClick={nextStep}
                className="flex items-center gap-1.5 px-6 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 font-medium text-sm text-white transition-colors"
              >
                Continue
                <ChevronRight size={16} />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSubmit}
                disabled={loading || !name.trim() || !bodyText.trim()}
                className="flex items-center gap-1.5 px-6 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 font-medium text-sm text-white transition-colors disabled:opacity-50"
              >
                {loading ? "Submitting..." : "Submit to WhatsApp"}
              </button>
            )}
          </div>
        </div>

        {/* Right Column: Sticky Live Preview */}
        <div className="lg:col-span-5 lg:sticky lg:top-6 space-y-4">
          {/* Removed Live WhatsApp Preview label */}
          <WhatsAppPreview
            headerType={headerType === "NONE" || headerType === "TEXT" ? undefined : headerType}
            headerText={headerType === "TEXT" ? headerText : undefined}
            headerMediaUrl={headerMediaUrl || undefined}
            bodyText={bodyText}
            footerText={footerText || undefined}
            buttons={buttons.map((b) => ({
              type: b.type,
              text: b.type === "ONE_TAP" ? (b.autofill_text || "Autofill") : b.text,
              url: b.url,
              phone: b.phone,
            }))}
          />
        </div>
      </div>
    </div>
  );
}
