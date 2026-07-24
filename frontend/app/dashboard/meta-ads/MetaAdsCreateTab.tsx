"use client";
import { useEffect, useState } from "react";
import { api, MetaAdsCreateSpec } from "@/lib/api";
import { useMetaAdsPages } from "@/hooks/useApi";
import { MessageCircle, Upload, Loader2 } from "lucide-react";
import { toast } from "sonner";

const inputCls = "h-9 w-full rounded-xl border border-surface-mid bg-white px-3 font-body text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200";
const labelCls = "mb-1 block font-label text-[10px] font-bold uppercase tracking-wider text-on-surface-muted";

export function MetaAdsCreateTab() {
  const { data: pagesData } = useMetaAdsPages();
  const pages = pagesData?.data ?? [];

  const [name, setName] = useState("");
  const [ageMin, setAgeMin] = useState(18);
  const [ageMax, setAgeMax] = useState(65);
  const [gender, setGender] = useState("all");
  const [budgetType, setBudgetType] = useState<"daily" | "lifetime">("daily");
  const [amount, setAmount] = useState<number>(500);
  const [message, setMessage] = useState("");
  const [headline, setHeadline] = useState("");
  const [greeting, setGreeting] = useState("Hi! I'm interested.");
  const [pageId, setPageId] = useState("");
  const [imageHash, setImageHash] = useState("");
  const [imagePreview, setImagePreview] = useState("");
  const [uploading, setUploading] = useState(false);
  const [publishing, setPublishing] = useState(false);

  useEffect(() => { if (pages.length && !pageId) setPageId(pages[0].id); }, [pages, pageId]);

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

  const canPublish = name && message && headline && greeting && pageId && imageHash && amount > 0;

  async function handlePublish() {
    if (!canPublish) return;
    setPublishing(true);
    try {
      const spec: MetaAdsCreateSpec = {
        name, creative_label: name, message, headline, greeting, image_hash: imageHash,
        page_id: pageId, location_countries: ["IN"], age_min: ageMin, age_max: ageMax, gender,
        daily_budget_inr: budgetType === "daily" ? amount : undefined,
        lifetime_budget_inr: budgetType === "lifetime" ? amount : undefined,
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

  return (
    <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
      {/* Form */}
      <div className="space-y-6">
        {/* Objective (locked) */}
        <section className="card rounded-2xl p-5">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-violet-50 text-violet-600"><MessageCircle size={22} /></div>
            <div>
              <h3 className="font-display text-base font-bold text-on-surface">Get WhatsApp messages</h3>
              <p className="font-body text-xs text-on-surface-muted">People tap your ad and land in a WhatsApp chat with you.</p>
            </div>
          </div>
        </section>

        {/* Audience */}
        <section className="card rounded-2xl p-5 space-y-4">
          <h3 className="font-display text-sm font-bold text-on-surface">Audience</h3>
          <div>
            <label className={labelCls}>Location</label>
            <input className={inputCls} value="India" disabled />
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
          <p className="font-body text-[11px] text-on-surface-muted">Placements and audience-finding are optimized automatically by Meta Advantage+.</p>
        </section>

        {/* Budget */}
        <section className="card rounded-2xl p-5 space-y-4">
          <h3 className="font-display text-sm font-bold text-on-surface">Budget &amp; schedule</h3>
          <div className="flex gap-2">
            {(["daily", "lifetime"] as const).map((b) => (
              <button key={b} onClick={() => setBudgetType(b)}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold ${budgetType === b ? "bg-primary text-white" : "bg-surface-low text-on-surface-muted"}`}>
                {b === "daily" ? "Daily" : "Total"}
              </button>
            ))}
          </div>
          <div>
            <label className={labelCls}>Amount (₹)</label>
            <input type="number" min={1} className={inputCls} value={amount} onChange={(e) => setAmount(+e.target.value)} />
          </div>
          <p className="rounded-lg bg-amber-50 px-3 py-2 font-body text-[11px] text-amber-700">💡 We recommend at least ₹1,500 total and 7 days so Meta can learn who to show your ad to.</p>
        </section>

        {/* Creative */}
        <section className="card rounded-2xl p-5 space-y-4">
          <h3 className="font-display text-sm font-bold text-on-surface">Creative</h3>
          <div><label className={labelCls}>Campaign name</label>
            <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Diwali Offer" /></div>
          <div><label className={labelCls}>Photo</label>
            <label className="flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-dashed border-surface-mid py-6 text-xs font-semibold text-on-surface-muted hover:bg-surface-low">
              {uploading ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
              {imageHash ? "Replace image" : "Upload image"}
              <input type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && handleUpload(e.target.files[0])} />
            </label></div>
          <div><label className={labelCls}>Ad text</label>
            <textarea className={`${inputCls} h-20 py-2`} value={message} onChange={(e) => setMessage(e.target.value)} placeholder="The message shown above your image" /></div>
          <div><label className={labelCls}>Headline</label>
            <input className={inputCls} value={headline} onChange={(e) => setHeadline(e.target.value)} /></div>
          <div><label className={labelCls}>Facebook Page</label>
            <select className={inputCls} value={pageId} onChange={(e) => setPageId(e.target.value)}>
              {pages.length === 0 && <option value="">No page available</option>}
              {pages.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select></div>
          <div><label className={labelCls}>Pre-filled greeting</label>
            <input className={inputCls} value={greeting} onChange={(e) => setGreeting(e.target.value)} />
            <p className="mt-1 font-body text-[11px] text-on-surface-muted">We add an invisible tracking tag to this automatically so replies attribute to this ad.</p></div>
        </section>

        <button onClick={handlePublish} disabled={!canPublish || publishing}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary py-3 font-label text-sm font-bold text-white transition-all hover:bg-primary/90 disabled:opacity-40">
          {publishing ? <Loader2 size={16} className="animate-spin" /> : null}
          {publishing ? "Publishing…" : "Publish campaign"}
        </button>
      </div>

      {/* Live preview */}
      <div className="lg:sticky lg:top-24 h-fit">
        <div className="card rounded-2xl p-4">
          <p className="mb-3 font-label text-[10px] font-bold uppercase tracking-wider text-on-surface-muted">Live preview</p>
          <div className="rounded-xl border border-surface-mid overflow-hidden">
            <div className="flex items-center gap-2 p-3">
              <div className="h-8 w-8 rounded-full bg-violet-100" />
              <span className="font-label text-xs font-bold text-on-surface">{pages.find((p) => p.id === pageId)?.name ?? "Your Page"}</span>
            </div>
            {imagePreview
              // eslint-disable-next-line @next/next/no-img-element
              ? <img src={imagePreview} alt="Ad preview" className="w-full object-cover" style={{ maxHeight: 220 }} />
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
      </div>
    </div>
  );
}
