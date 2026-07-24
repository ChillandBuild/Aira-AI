"use client";
import { useEffect, useState, type ReactNode } from "react";
import { api, MetaAdsCreateSpec } from "@/lib/api";
import { useMetaAdsPages } from "@/hooks/useApi";
import {
  MessageCircle, Upload, Loader2, Check, MapPin, Wallet, Image as ImageIcon,
  ClipboardCheck, Megaphone, ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const inputCls = "h-10 w-full rounded-xl border border-surface-mid bg-white px-3 font-body text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200 disabled:bg-surface-low disabled:text-on-surface-muted";
const labelCls = "mb-1.5 block font-label text-[10px] font-bold uppercase tracking-wider text-on-surface-muted";

// Meta special_ad_categories enum values, matching the screenshots' declare list.
const SPECIAL_CATEGORIES: { value: string; label: string }[] = [
  { value: "", label: "Not applicable (most ads)" },
  { value: "FINANCIAL_PRODUCTS_SERVICES", label: "Financial products and services" },
  { value: "EMPLOYMENT", label: "Employment" },
  { value: "HOUSING", label: "Housing" },
  { value: "ISSUES_ELECTIONS_POLITICS", label: "Social issues, elections or politics" },
];

const STEPS = [
  { key: "campaign", label: "Campaign", icon: Wallet },
  { key: "adset", label: "Ad set", icon: MapPin },
  { key: "ad", label: "Ad", icon: ImageIcon },
  { key: "review", label: "Review", icon: ClipboardCheck },
];

function money(n: number) {
  return "₹" + Math.round(n).toLocaleString("en-IN");
}

export function MetaAdsCreateTab() {
  const { data: pagesData } = useMetaAdsPages();
  const pages = pagesData?.data ?? [];

  const [step, setStep] = useState(0); // 0=Campaign 1=AdSet 2=Ad 3=Review

  // Campaign
  const [name, setName] = useState("");
  const [budgetType, setBudgetType] = useState<"daily" | "lifetime">("daily");
  const [amount, setAmount] = useState<number>(500);
  const [specialCategory, setSpecialCategory] = useState("");

  // Ad set
  const [pageId, setPageId] = useState("");
  const [waNumber, setWaNumber] = useState<string>("");
  const [ageMin, setAgeMin] = useState(18);
  const [ageMax, setAgeMax] = useState(65);
  const [gender, setGender] = useState("all");

  // Ad
  const [message, setMessage] = useState("");
  const [headline, setHeadline] = useState("");
  const [greeting, setGreeting] = useState("Hi! I'm interested.");
  const [imageHash, setImageHash] = useState("");
  const [imagePreview, setImagePreview] = useState("");
  const [uploading, setUploading] = useState(false);

  const [publishing, setPublishing] = useState(false);

  useEffect(() => { if (pages.length && !pageId) setPageId(pages[0].id); }, [pages, pageId]);
  useEffect(() => {
    api.metaAds.whatsappNumbers().then((r) => setWaNumber(r.data[0]?.number ?? "")).catch(() => undefined);
  }, []);

  const campaignDone = !!name.trim() && amount > 0;
  const adsetDone = !!pageId;
  const adDone = !!imageHash && !!message.trim() && !!headline.trim() && !!greeting.trim();
  const stepDone = [campaignDone, adsetDone, adDone, true];
  const canPublish = campaignDone && adsetDone && adDone;

  async function handleUpload(file: File) {
    setUploading(true);
    try {
      const res = await api.metaAds.uploadMedia(file);
      if (res.image_hash) {
        setImageHash(res.image_hash);
        setImagePreview(URL.createObjectURL(file));
        toast.success("Image uploaded");
      } else {
        toast.error(res.error ?? "Upload failed");
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handlePublish() {
    if (!canPublish) return;
    setPublishing(true);
    try {
      const spec: MetaAdsCreateSpec = {
        name, creative_label: name, message, headline, greeting, image_hash: imageHash,
        page_id: pageId, location_countries: ["IN"], age_min: ageMin, age_max: ageMax, gender,
        daily_budget_inr: budgetType === "daily" ? amount : undefined,
        lifetime_budget_inr: budgetType === "lifetime" ? amount : undefined,
        special_ad_category: specialCategory || null,
      };
      const res = await api.metaAds.createCampaign(spec);
      if (res.ok) toast.success("Campaign submitted to Meta — review takes ~24h.");
      else toast.error(res.error ?? "Publish failed");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Publish failed");
    } finally {
      setPublishing(false);
    }
  }

  function goNext() { if (step < STEPS.length - 1 && stepDone[step]) setStep(step + 1); }
  function goBack() { if (step > 0) setStep(step - 1); }

  return (
    <div className="mx-auto max-w-6xl">
      {/* Objective banner + step indicator (uses the space freed by the header title) */}
      <div className="mb-6 rounded-2xl border border-surface-mid bg-white p-4 md:p-5">
        <div className="flex items-center gap-3 border-b border-surface-mid/60 pb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-50 text-violet-600"><MessageCircle size={20} /></div>
          <div className="min-w-0">
            <p className="font-label text-[10px] font-bold uppercase tracking-wider text-on-surface-muted">Campaign objective</p>
            <h3 className="font-display text-sm font-bold text-on-surface">Get WhatsApp messages · Click-to-WhatsApp</h3>
          </div>
          <span className="ml-auto hidden rounded-full bg-emerald-50 px-2.5 py-1 font-label text-[11px] font-bold text-emerald-700 sm:inline">Advantage+ on</span>
        </div>
        <StepIndicator step={step} stepDone={stepDone} onJump={(i) => { if (i <= step || stepDone.slice(0, i).every(Boolean)) setStep(i); }} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        {/* Step content */}
        <div className="min-w-0">
          {step === 0 && (
            <div className="space-y-5">
              <Section title="Campaign details" sub="Name your campaign and set how much you want to spend.">
                <div>
                  <label className={labelCls}>Campaign name</label>
                  <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Diwali Offer" />
                </div>
                <div>
                  <label className={labelCls}>Buying type</label>
                  <input className={inputCls} value="Auction" disabled />
                </div>
              </Section>

              <Section title="Budget" badge="Campaign budget · Advantage+" sub="Meta automatically spreads this budget across the best opportunities.">
                <div className="flex gap-2">
                  {(["daily", "lifetime"] as const).map((b) => (
                    <button key={b} onClick={() => setBudgetType(b)}
                      className={cn("rounded-xl px-4 py-2 font-label text-xs font-bold transition-all",
                        budgetType === b ? "bg-primary text-white shadow-sm" : "bg-surface-low text-on-surface-muted hover:bg-surface-mid/40")}>
                      {b === "daily" ? "Daily budget" : "Total (lifetime)"}
                    </button>
                  ))}
                </div>
                <div>
                  <label className={labelCls}>Amount (₹)</label>
                  <div className="relative">
                    <input type="number" min={1} className={cn(inputCls, "pl-7")} value={amount} onChange={(e) => setAmount(+e.target.value)} />
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-on-surface-muted">₹</span>
                  </div>
                  <p className="mt-1.5 font-body text-[11px] text-on-surface-muted">Bid strategy: <span className="font-semibold text-on-surface">Highest volume</span> (automatic).</p>
                </div>
                <p className="rounded-lg bg-amber-50 px-3 py-2 font-body text-[11px] text-amber-700">💡 We recommend at least ₹1,500 total and 7 days so Meta can learn who to show your ad to.</p>
              </Section>

              <Section title="Special Ad Categories" sub="Declare if this ad relates to credit, employment, housing or social issues — it prevents rejections.">
                <div>
                  <label className={labelCls}>Declare category if applicable</label>
                  <select className={inputCls} value={specialCategory} onChange={(e) => setSpecialCategory(e.target.value)}>
                    {SPECIAL_CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                  </select>
                </div>
              </Section>
            </div>
          )}

          {step === 1 && (
            <div className="space-y-5">
              <Section title="Conversion" sub="Where people land after tapping your ad.">
                <div>
                  <label className={labelCls}>Conversion location</label>
                  <input className={inputCls} value="WhatsApp" disabled />
                </div>
                <div>
                  <label className={labelCls}>Performance goal</label>
                  <input className={inputCls} value="Maximize number of conversations" disabled />
                </div>
                <div>
                  <label className={labelCls}>Facebook Page</label>
                  <select className={inputCls} value={pageId} onChange={(e) => setPageId(e.target.value)}>
                    {pages.length === 0 && <option value="">No page available — connect one in Meta</option>}
                    {pages.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className={labelCls}>WhatsApp number</label>
                  <input className={inputCls} value={waNumber || "No active WhatsApp number"} disabled />
                  <p className="mt-1.5 font-body text-[11px] text-on-surface-muted">Messages route to your primary WhatsApp number automatically.</p>
                </div>
              </Section>

              <Section title="Audience" badge="Advantage+ on" sub="Meta finds the right people within these bounds. Placements are optimized automatically.">
                <div>
                  <label className={labelCls}>Location</label>
                  <div className="flex items-center gap-2 rounded-xl border border-surface-mid bg-surface-low px-3 py-2.5">
                    <MapPin size={15} className="text-violet-500" />
                    <span className="font-body text-sm font-semibold text-on-surface">India</span>
                    <span className="ml-auto font-label text-[10px] font-bold uppercase tracking-wider text-on-surface-muted">Fixed</span>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <div><label className={labelCls}>Age min</label>
                    <input type="number" min={13} max={65} className={inputCls} value={ageMin} onChange={(e) => setAgeMin(+e.target.value)} /></div>
                  <div><label className={labelCls}>Age max</label>
                    <input type="number" min={13} max={65} className={inputCls} value={ageMax} onChange={(e) => setAgeMax(+e.target.value)} /></div>
                  <div><label className={labelCls}>Gender</label>
                    <select className={inputCls} value={gender} onChange={(e) => setGender(e.target.value)}>
                      <option value="all">All</option><option value="male">Men</option><option value="female">Women</option>
                    </select></div>
                </div>
              </Section>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-5">
              <Section title="Ad creative" sub="The photo and text people see in their feed.">
                <div>
                  <label className={labelCls}>Photo</label>
                  <label className="flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-dashed border-surface-mid py-8 text-xs font-semibold text-on-surface-muted transition-colors hover:bg-surface-low">
                    {uploading ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
                    {imageHash ? "Replace image" : "Upload image"}
                    <input type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && handleUpload(e.target.files[0])} />
                  </label>
                </div>
                <div><label className={labelCls}>Ad text</label>
                  <textarea className={cn(inputCls, "h-20 py-2")} value={message} onChange={(e) => setMessage(e.target.value)} placeholder="The message shown above your image" /></div>
                <div><label className={labelCls}>Headline</label>
                  <input className={inputCls} value={headline} onChange={(e) => setHeadline(e.target.value)} placeholder="A short, punchy line" /></div>
              </Section>

              <Section title="Conversation" sub="What people see when the WhatsApp chat opens.">
                <div><label className={labelCls}>Pre-filled greeting</label>
                  <input className={inputCls} value={greeting} onChange={(e) => setGreeting(e.target.value)} />
                  <p className="mt-1.5 font-body text-[11px] text-on-surface-muted">We add an invisible tracking tag to this automatically so replies attribute to this ad.</p></div>
              </Section>
            </div>
          )}

          {step === 3 && (
            <Section title="Review" sub="Check everything, then publish. Meta reviews new ads within ~24h.">
              <div className="divide-y divide-surface-mid/60">
                <ReviewRow label="Campaign name" value={name || "—"} />
                <ReviewRow label="Objective" value="Get WhatsApp messages (Engagement)" />
                <ReviewRow label="Buying type" value="Auction" />
                <ReviewRow label="Budget" value={`${money(amount)} ${budgetType === "daily" ? "/ day" : "total"} · Campaign budget`} />
                <ReviewRow label="Bid strategy" value="Highest volume" />
                <ReviewRow label="Special ad category" value={SPECIAL_CATEGORIES.find((c) => c.value === specialCategory)?.label ?? "Not applicable"} />
                <ReviewRow label="Facebook Page" value={pages.find((p) => p.id === pageId)?.name ?? "—"} />
                <ReviewRow label="WhatsApp number" value={waNumber || "—"} />
                <ReviewRow label="Audience" value={`India · Age ${ageMin}–${ageMax} · ${gender === "all" ? "All genders" : gender === "male" ? "Men" : "Women"}`} />
                <ReviewRow label="Creative" value={imageHash ? "Image uploaded" : "No image"} />
              </div>
              {!canPublish && (
                <p className="mt-3 flex items-center gap-1.5 rounded-lg bg-amber-50 px-3 py-2 font-body text-[11px] text-amber-700">
                  <ChevronRight size={13} /> Complete the highlighted steps above before publishing.
                </p>
              )}
            </Section>
          )}

          {/* Nav bar */}
          <div className="mt-6 flex items-center justify-between">
            <button onClick={goBack} disabled={step === 0}
              className="rounded-xl border border-surface-mid bg-white px-5 py-2.5 font-label text-sm font-bold text-on-surface transition-colors hover:bg-surface-low disabled:opacity-40">
              Back
            </button>
            {step < STEPS.length - 1 ? (
              <button onClick={goNext} disabled={!stepDone[step]}
                className="flex items-center gap-2 rounded-xl bg-primary px-6 py-2.5 font-label text-sm font-bold text-white transition-all hover:bg-primary/90 disabled:opacity-40">
                Next <ChevronRight size={15} />
              </button>
            ) : (
              <button onClick={handlePublish} disabled={!canPublish || publishing}
                className="flex items-center gap-2 rounded-xl bg-primary px-6 py-2.5 font-label text-sm font-bold text-white transition-all hover:bg-primary/90 disabled:opacity-40">
                {publishing ? <Loader2 size={16} className="animate-spin" /> : <Megaphone size={15} />}
                {publishing ? "Publishing…" : "Publish campaign"}
              </button>
            )}
          </div>
        </div>

        {/* Sticky live preview + setup checklist */}
        <div className="lg:sticky lg:top-24 h-fit space-y-4">
          <div className="rounded-2xl border border-surface-mid bg-white p-4">
            <p className="mb-3 font-label text-[10px] font-bold uppercase tracking-wider text-on-surface-muted">Live preview</p>
            <div className="overflow-hidden rounded-xl border border-surface-mid">
              <div className="flex items-center gap-2 p-3">
                <div className="h-8 w-8 rounded-full bg-violet-100" />
                <span className="font-label text-xs font-bold text-on-surface">{pages.find((p) => p.id === pageId)?.name ?? "Your Page"}</span>
              </div>
              {imagePreview
                // eslint-disable-next-line @next/next/no-img-element
                ? <img src={imagePreview} alt="Ad preview" className="w-full object-cover" style={{ maxHeight: 200 }} />
                : <div className="flex h-40 items-center justify-center bg-surface-low text-xs text-on-surface-muted">Image preview</div>}
              <div className="p-3">
                <p className="font-body text-sm text-on-surface">{message || "Your ad text appears here."}</p>
                <p className="mt-1 font-label text-xs font-bold text-on-surface">{headline || "Headline"}</p>
                <button className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg bg-[#25D366] py-2 text-xs font-bold text-white">
                  <MessageCircle size={14} /> Send Message
                </button>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-surface-mid bg-white p-4">
            <p className="mb-3 font-label text-[10px] font-bold uppercase tracking-wider text-on-surface-muted">Setup checklist</p>
            <ul className="space-y-2.5">
              {STEPS.slice(0, 3).map((s, i) => (
                <li key={s.key} className="flex items-center gap-2.5">
                  <span className={cn("flex h-5 w-5 items-center justify-center rounded-full",
                    stepDone[i] ? "bg-emerald-100 text-emerald-600" : "bg-surface-low text-on-surface-muted")}>
                    {stepDone[i] ? <Check size={12} strokeWidth={3} /> : <s.icon size={12} />}
                  </span>
                  <span className={cn("font-body text-sm", stepDone[i] ? "text-on-surface" : "text-on-surface-muted")}>{s.label}</span>
                  {i === step && <span className="ml-auto font-label text-[10px] font-bold uppercase tracking-wider text-primary">Editing</span>}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

function StepIndicator({ step, stepDone, onJump }:
  { step: number; stepDone: boolean[]; onJump: (i: number) => void }) {
  return (
    <div className="mt-4 flex items-center">
      {STEPS.map((s, i) => {
        const done = stepDone[i] && i < step;
        const active = i === step;
        return (
          <div key={s.key} className="flex flex-1 items-center last:flex-none">
            <button onClick={() => onJump(i)} className="flex flex-col items-center gap-1.5">
              <span className={cn("flex h-9 w-9 items-center justify-center rounded-full font-bold text-sm transition-all",
                done ? "bg-gradient-to-br from-[#2e1065] to-primary text-white"
                  : active ? "bg-gradient-to-br from-[#2e1065] to-primary text-white ring-4 ring-primary/20"
                  : "border-2 border-surface-mid bg-surface text-on-surface-muted")}>
                {done ? <Check size={15} /> : i + 1}
              </span>
              <span className={cn("font-label text-[11px]", active ? "font-bold text-primary" : done ? "text-primary/60" : "text-on-surface-muted")}>{s.label}</span>
            </button>
            {i < STEPS.length - 1 && (
              <div className={cn("mx-2 h-0.5 flex-1 rounded-full transition-colors", i < step ? "bg-primary" : "bg-surface-mid")} />
            )}
          </div>
        );
      })}
    </div>
  );
}

function Section({ title, sub, badge, children }:
  { title: string; sub?: string; badge?: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-surface-mid bg-white p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 className="font-display text-sm font-bold text-on-surface">{title}</h3>
          {sub && <p className="mt-0.5 font-body text-[11px] text-on-surface-muted">{sub}</p>}
        </div>
        {badge && <span className="shrink-0 rounded-full bg-emerald-50 px-2.5 py-1 font-label text-[10px] font-bold text-emerald-700">{badge}</span>}
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

function ReviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5">
      <span className="font-label text-xs font-bold uppercase tracking-wider text-on-surface-muted">{label}</span>
      <span className="text-right font-body text-sm font-semibold text-on-surface">{value}</span>
    </div>
  );
}
