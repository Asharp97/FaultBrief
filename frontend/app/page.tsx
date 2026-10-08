"use client";

import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import {
  ArrowDown, ArrowRight, ArrowUpRight, Braces, Check, ChevronDown,
  CircleDot, FileText, Fingerprint, GitBranch, Layers3, LockKeyhole,
  Menu, Play, RotateCcw, ScanLine, Search, ShieldCheck, Workflow, X,
} from "lucide-react";

gsap.registerPlugin(useGSAP, ScrollTrigger);

const cases = [
  {
    name: "Permissions", icon: LockKeyhole, tag: "FB-001", topic: "Report download",
    ticket: "I could download our reports yesterday. Today I get ‘access denied’. Is something down?",
    customer: "Acme Studio", role: "Account administration",
    steps: ["Read customer context", "Check service health", "Inspect access settings", "Build the evidence brief"],
    evidence: [
      { source: "Service health", value: "Report service operational" },
      { source: "Account entitlement", value: "Downloads included in current plan" },
      { source: "Permission history", value: "report.download removed from user role" },
    ],
    finding: "A role change removed download access.",
    explanation: "The service is healthy and the account includes downloads. The permission history points to a user-level access change.",
    next: "Ask the account administrator to review the role change before restoring access.",
  },
  {
    name: "Feature settings", icon: Layers3, tag: "FB-002", topic: "Scheduled reports",
    ticket: "Our scheduled reports stopped arriving, but I can still generate one manually. What changed?",
    customer: "Northline Labs", role: "Product support",
    steps: ["Read customer context", "Check manual report status", "Inspect feature settings", "Build the evidence brief"],
    evidence: [
      { source: "Manual report log", value: "Report generated successfully" },
      { source: "Scheduler health", value: "Scheduler operational" },
      { source: "Configuration history", value: "Scheduled reports disabled for this account" },
    ],
    finding: "Scheduled reports are disabled for this account.",
    explanation: "Manual generation and the scheduler are working. The account configuration shows scheduling was turned off.",
    next: "Have product support confirm the intended configuration with the customer.",
  },
  {
    name: "Background jobs", icon: Workflow, tag: "FB-003", topic: "Export queue",
    ticket: "My export is stuck on ‘processing’. I’ve retried twice and nothing has arrived.",
    customer: "Fieldwork Co.", role: "Engineering",
    steps: ["Read customer context", "Inspect export job", "Check worker heartbeat", "Build the evidence brief"],
    evidence: [
      { source: "Job record", value: "Job queued; processing has not started" },
      { source: "Permission check", value: "Export permission granted" },
      { source: "Worker health", value: "Worker heartbeat missing in sample scenario" },
    ],
    finding: "The evidence points to an unavailable export worker.",
    explanation: "The job is waiting in the queue and access is valid. A missing worker heartbeat supports an availability hypothesis; engineering should verify it.",
    next: "Escalate the job record and worker health evidence to engineering.",
  },
];

const principles = [
  { icon: Fingerprint, title: "The right customer context", text: "Keep an investigation tied to the affected account, its settings, and the issue at hand." },
  { icon: Search, title: "Checks before conclusions", text: "Gather relevant records through a small set of controlled diagnostic tools." },
  { icon: FileText, title: "Evidence you can inspect", text: "Bring the supporting records into the brief, so a human can review the finding." },
  { icon: ShieldCheck, title: "Read-only by design", text: "The first release is designed to investigate and recommend, with people in control of changes." },
  { icon: GitBranch, title: "A useful handoff", text: "Suggest the appropriate team and carry the context forward instead of starting again." },
  { icon: CircleDot, title: "Room for uncertainty", text: "An inconclusive result is useful when the evidence does not establish a cause." },
];

export default function Home() {
  const root = useRef<HTMLElement>(null);
  const playback = useRef<gsap.core.Timeline | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [selected, setSelected] = useState(0);
  const [step, setStep] = useState(-1);
  const [state, setState] = useState<"ready" | "running" | "complete">("ready");
  const current = cases[selected];

  useGSAP(() => {
    const media = gsap.matchMedia();
    media.add("(prefers-reduced-motion: no-preference)", () => {
      gsap.from("[data-hero]", { y: 26, opacity: 0, duration: 0.85, stagger: 0.1, ease: "power3.out" });
      gsap.utils.toArray<HTMLElement>("[data-reveal]").forEach((element) => {
        gsap.from(element, {
          y: 28, opacity: 0, duration: 0.75, ease: "power3.out",
          scrollTrigger: { trigger: element, start: "top 90%", once: true },
        });
      });
    });
    return () => media.revert();
  }, { scope: root });

  useEffect(() => () => { playback.current?.kill(); }, []);

  function selectCase(index: number) {
    playback.current?.kill();
    setSelected(index);
    setState("ready");
    setStep(-1);
  }

  function runSample() {
    playback.current?.kill();
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setStep(4);
      setState("complete");
      return;
    }
    setState("running");
    setStep(0);
    const timeline = gsap.timeline({ onComplete: () => { setStep(4); setState("complete"); } });
    for (let index = 1; index <= 4; index += 1) {
      timeline.to({}, { duration: 0.55 }).call(() => setStep(index));
    }
    playback.current = timeline;
  }

  function closeMenu() { setMenuOpen(false); }

  return (
    <main ref={root} className="min-h-screen bg-paper text-ink">
      <a href="#main-content" className="skip-link">Skip to content</a>
      <header className="site-header shell flex items-center justify-between">
        <a className="wordmark" href="#" aria-label="FaultBrief home"><span className="brand-glyph"><ScanLine size={23} strokeWidth={1.4} /></span>FaultBrief<span className="brand-stop">.</span></a>
        <nav className="desktop-nav" aria-label="Main navigation">
          <a href="#product">Product</a><a href="#workflow">How it works</a><a href="#principles">Principles</a>
        </nav>
        <div className="header-actions"><span className="prototype-label">A product in progress</span><a className="button button-teal button-small" href="#product">Try the sample <ArrowUpRight size={15} /></a></div>
        <button className="mobile-toggle" aria-label={menuOpen ? "Close navigation" : "Open navigation"} aria-expanded={menuOpen} aria-controls="mobile-navigation" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X size={22} /> : <Menu size={22} />}</button>
        {menuOpen && <nav id="mobile-navigation" className="mobile-nav" aria-label="Mobile navigation"><a onClick={closeMenu} href="#product">Product</a><a onClick={closeMenu} href="#workflow">How it works</a><a onClick={closeMenu} href="#principles">Principles</a><a onClick={closeMenu} href="#product">Try the sample <ArrowUpRight size={16} /></a></nav>}
      </header>

      <section id="main-content" className="hero shell">
        <div className="hero-eyebrow" data-hero><span className="status-dot" />AI SUPPORT INVESTIGATION<span className="eyebrow-rule" />CONCEPT PREVIEW</div>
        <div className="hero-layout">
          <div>
            <h1 className="font-display font-normal" data-hero>Follow the evidence.<br /><span className="italic-headline">Find the next step.</span></h1>
            <p className="hero-copy" data-hero>A customer says something broke. FaultBrief is designed to gather the context, explain what the evidence supports, and give your team a clearer place to start.</p>
            <div className="hero-actions flex items-center" data-hero><a className="button button-ink" href="#product">Explore an investigation <ArrowUpRight size={17} /></a><a className="text-link" href="#workflow">How it works <ArrowDown size={15} /></a></div>
          </div>
          <div className="hero-note" data-hero><div className="note-mark"><Braces size={24} strokeWidth={1.3} /></div><p>Less guesswork.<br />More context.<br /><span>A better handoff.</span></p><div className="note-foot">TICKET → EVIDENCE → BRIEF</div></div>
        </div>
        <div className="hero-bottom" data-hero><span>Built around the issue.<br /><strong>Grounded in the records.</strong></span><span className="hero-index">01 / THE INVESTIGATION</span><a href="#product" className="circle-link" aria-label="Scroll to the investigation preview"><ArrowDown size={20} /></a></div>
      </section>

      <section id="product" className="product-section shell">
        <div className="section-intro" data-reveal><div><p className="eyebrow">A SMALL ISSUE. A CLEARER PICTURE.</p><h2>See the trail<br />come together.</h2></div><p>Follow a sample ticket through customer context, diagnostic checks, and a brief a support engineer can review.</p></div>
        <div className="investigation-demo" data-reveal>
          <div className="demo-chrome"><div className="chrome-dots" aria-hidden="true"><span /><span /><span /></div><span>faultbrief / investigation preview</span><span className="sample-badge">SYNTHETIC DATA</span></div>
          <div className="case-tabs" role="group" aria-label="Choose a sample issue">{cases.map((item, index) => { const Icon = item.icon; return <button key={item.name} onClick={() => selectCase(index)} aria-pressed={selected === index} className={selected === index ? "case-tab active" : "case-tab"}><Icon size={17} strokeWidth={1.6} />{item.name}</button>; })}</div>
          <div className="demo-layout">
            <div className="ticket-pane flex flex-col">
              <div className="pane-label"><span>THE CUSTOMER TICKET</span><span>{current.tag}</span></div>
              <h3>{current.topic}</h3><p className="ticket-quote">“{current.ticket}”</p><div className="ticket-customer"><span className="customer-avatar">{current.customer[0]}</span><div>{current.customer}<span>Sample customer account</span></div></div>
              <div className="ticket-controls"><button className="button button-teal" onClick={runSample} disabled={state === "running"}>{state === "complete" ? <RotateCcw size={15} /> : <Play size={15} fill="currentColor" />}{state === "running" ? "Following the evidence…" : state === "complete" ? "Replay sample" : "Run sample"}</button><span>Illustrative playback.<br />No live systems connected.</span></div>
            </div>
            <div className="trace-pane"><div className="pane-label"><span>INVESTIGATION TRAIL</span><span className="trace-state">{state === "complete" ? "COMPLETE" : state === "running" ? "IN PROGRESS" : "READY"}</span></div><ol className="trace-list">{current.steps.map((label, index) => <li key={label} className={step > index ? "trace-step done" : step === index ? "trace-step current" : "trace-step"}><span className="step-icon">{step > index ? <Check size={12} /> : String(index + 1).padStart(2, "0")}</span><span>{label}</span><span className="step-status">{step > index ? "checked" : step === index ? "reading" : "pending"}</span></li>)}</ol><div className="evidence-records">{step >= 2 ? current.evidence.map((record) => <div key={record.source}><span>{record.source}</span><p>{record.value}</p></div>) : <div className="waiting-evidence"><FileText size={23} strokeWidth={1.3} /><span>The supporting records<br />will appear here.</span></div>}</div></div>
          </div>
          <div className={state === "complete" ? "brief-result visible" : "brief-result"} aria-live="polite" aria-atomic="true">{state === "complete" ? <><div className="brief-heading"><span className="eyebrow">THE EVIDENCE BRIEF</span><span className="handoff-label"><GitBranch size={14} />{current.role}</span></div><h3>{current.finding}</h3><p>{current.explanation}</p><div className="brief-next"><ArrowRight size={16} /><span>{current.next}</span></div></> : <div className="brief-placeholder"><span className="status-dot" /><span>{state === "running" ? "Gathering the sample evidence before drawing a conclusion." : "Run a sample to see a finding and a suggested handoff."}</span></div>}</div>
        </div>
        <p className="demo-disclosure">This interactive preview uses prepared scenarios. Live integrations and model-driven investigations are part of the planned product.</p>
      </section>

      <section id="workflow" className="workflow-section shell">
        <div className="section-intro" data-reveal><div><p className="eyebrow">FROM “IT BROKE” TO “HERE’S WHAT WE KNOW”</p><h2>A brief, not<br />another black box.</h2></div><p>The proposed workflow keeps the useful parts of an investigation together, with a person reviewing the result.</p></div>
        <div className="workflow-grid" data-reveal>{[
          ["01", "Start with the issue", "Describe the problem and identify the affected customer. Give the investigation a specific starting point."],
          ["02", "Gather the context", "Check the permitted settings, relevant logs, job records, and runbooks for that customer."],
          ["03", "Build the case", "Separate observations from hypotheses. Keep the evidence attached and the unknowns visible."],
          ["04", "Hand it to a human", "Review the brief and suggested next step. Route it to the team best placed to act."],
        ].map(([number, title, text]) => <article key={number}><div className="workflow-number">{number}<ArrowUpRight size={17} /></div><h3>{title}</h3><p>{text}</p></article>)}</div>
      </section>

      <section className="statement-section" data-reveal><div className="shell statement-inner"><span className="eyebrow">THE QUESTION THAT STARTED FAULTBRIEF</span><h2>“Why is it broken<br />for <em>this</em> customer?”</h2><p>A healthy service does not always mean a working customer experience.<br className="desktop-break" /> Permissions, configuration, and background jobs are a good place to start.</p><div className="statement-symbol" aria-hidden="true"><Fingerprint size={126} strokeWidth={0.65} /></div></div></section>

      <section id="principles" className="principles-section shell"><div className="section-intro" data-reveal><div><p className="eyebrow">DESIGNED FOR THE WAY SUPPORT WORKS</p><h2>Useful findings.<br />Visible foundations.</h2></div><p>These are the principles guiding the first release: a focused investigation, an inspectable result, and a thoughtful handoff.</p></div><div className="feature-grid" data-reveal>{principles.map(({ icon: Icon, title, text }) => <article key={title}><Icon size={25} strokeWidth={1.35} /><h3>{title}</h3><p>{text}</p></article>)}</div></section>

      <section className="faq-section shell"><div data-reveal><p className="eyebrow">A FEW GOOD QUESTIONS</p><h2>Before the<br />investigation.</h2></div><div className="faq-list" data-reveal>{[
        ["Is the preview connected to a real service?", "No. The examples use prepared, synthetic records to demonstrate the proposed investigation flow. Running a sample does not call a language model or access a customer system."],
        ["Will FaultBrief change customer settings?", "The first release is planned as a read-only investigator. It gathers evidence and recommends next steps for a human to review."],
        ["What happens if the evidence is incomplete?", "The product is designed to return an inconclusive finding and identify the missing information, rather than present a guess as a confirmed cause."],
        ["How would a team connect its application?", "The planned integration uses scoped diagnostic APIs or approved connectors for settings, logs, and job status. Access is configured by the team, with credentials kept on the backend."],
      ].map(([question, answer]) => <details key={question}><summary>{question}<ChevronDown size={18} /></summary><p>{answer}</p></details>)}</div></section>

      <section className="closing-section shell" data-reveal><div className="closing-panel"><div><span className="closing-label">LESS GUESSWORK. A CLEARER NEXT STEP.</span><h2>Every issue<br />deserves a little context.</h2></div><div className="closing-copy"><p>See how a ticket, a few useful checks, and an evidence brief can fit together.</p><a className="button button-ink" href="#product">Follow a sample investigation <ArrowUpRight size={17} /></a></div><div className="closing-grid" aria-hidden="true" /></div></section>

      <footer className="site-footer shell"><a className="wordmark" href="#">FaultBrief<span className="brand-stop">.</span></a><p>A clearer story behind the support ticket.</p><div><a href="#product">Product preview <ArrowUpRight size={13} /></a><span>© 2026 FaultBrief</span></div></footer>
    </main>
  );
}
