import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { request } from "../lib/api";
import { BaseAccordion, BaseButton, BaseCheckbox, BaseSelect, BaseSlider, BaseTabs } from "./BaseControls";

type Channel = { id: string; name: string; style_preset: string; aspect_ratio: string; resolution: string; settings_json: Record<string, any> };
type Character = { id: string; channel_id: string; name: string; presenter_provider: string; provider_avatar_id: string | null; reference_image_path: string | null; voice_provider: string; voice_id: string | null; settings_json: Record<string, any> };
type Production = { id: string; channel_id: string; name: string; script: string; state: string; error?: string; expected_duration: number; final_duration?: number; production_json: Record<string, any> };
type Job = { id: string; project_id: string; state: string; progress: number; error?: string; attempts: number; max_attempts: number; payload_json: {stage?: string} };
type Workspace = { channels: Channel[]; characters: Character[]; projects: Production[]; jobs: Job[]; usage: { finished_minutes: number; reported_cost_usd: number; concurrent_projects: number; cost_note: string }; commercial?: any };
type Review = { duration: number; word_count: number; ready: boolean; presenter_guard_estimate_usd: number; blockers: string[]; warnings: string[]; timing_note: string; cost_note: string; scenes: { ordinal: number; start: number; end: number; type: string; narration: string; visual_prompt: string }[] };
const initialOptions = { name: "", script: "", avatar_id: "", words_per_minute: 145, scene_seconds: 12, presenter_target: .3,
  aspect_ratio: "16:9", resolution: "1080p", budget_usd: 50, visual_style: "Cinematic documentary, natural lighting, consistent warm colors",
  captions: true, caption_size: 22, background_color: "#f4d2dc", music_path: "", narration_path: "", music_volume: .12,
  music_strategy: "off", music_mood: "calm documentary", transition_style: "crossfade", scene_direction_mode: "assisted", mode: "production" };
const blankCharacter = { name: "", presenter_provider: "authorized_higgsfield", provider_avatar_id: "", reference_image_path: "", voice_provider: "ai33", voice_id: "", persona: "Warm, clear and trustworthy", language: "English", appearance: "", consent: false };
const seconds = (n: number) => `${Math.floor(n / 60)}:${Math.round(n % 60).toString().padStart(2, "0")}`;
const exportUrl = (id: string, kind: string) => `http://127.0.0.1:8765/studio/productions/${encodeURIComponent(id)}/files/${kind}`;

export function ChannelStudio() {
  const [tab, setTab] = useState("create");
  const [data, setData] = useState<Workspace | null>(null);
  const [channelId, setChannelId] = useState("");
  const [options, setOptions] = useState(initialOptions);
  const [review, setReview] = useState<Review | null>(null);
  const [draftId, setDraftId] = useState<string | null>(null);
  const [character, setCharacter] = useState(blankCharacter);
  const [editingCharacter, setEditingCharacter] = useState<string | null>(null);
  const [channelName, setChannelName] = useState("");
  const [niche, setNiche] = useState("");
  const [brand, setBrand] = useState("Cinematic documentary");
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [voicePreviewUrl, setVoicePreviewUrl] = useState("");
  const [directionBusy, setDirectionBusy] = useState(false);
  const [approved, setApproved] = useState(false);
  const [selected, setSelected] = useState<Production | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const refresh = useCallback(async () => {
    const next = await request<Workspace>("/studio/workspace");
    setData(next);
    setChannelId(current => current || next.channels[0]?.id || "");
    return next;
  }, []);
  useEffect(() => { void refresh().catch(e => setError(e.message)); }, [refresh]);
  useEffect(() => {
    if (!data?.jobs.some(j => ["QUEUED", "RUNNING"].includes(j.state))) return;
    const timer = window.setInterval(() => void refresh().catch(e => setError(e.message)), 3000);
    return () => window.clearInterval(timer);
  }, [data?.jobs, refresh]);
  useEffect(() => {
    if (selected) void request(`/studio/productions/${selected.id}`).then(setDetail).catch(e => setError(e.message));
  }, [selected, data?.jobs]);
  async function work(action: () => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true; setBusy(true); setError(""); setNotice("");
    try { await action(); } catch(e) { setError(e instanceof Error ? e.message : "Could not complete this action"); }
    finally { busyRef.current = false; setBusy(false); }
  }
  function change(key: keyof typeof initialOptions, value: string | number | boolean) {
    setOptions(old => ({ ...old, [key]: value })); setReview(null); setDraftId(null); setApproved(false);
  }
  function chooseChannel(id: string) {
    const channel = data?.channels.find(c => c.id === id);
    setChannelId(id); setReview(null); setDraftId(null); setApproved(false);
    setOptions(old => ({...old, avatar_id: "", aspect_ratio: channel?.aspect_ratio || "16:9", resolution: channel?.resolution || "1080p",
      visual_style: channel?.settings_json.visual_style || old.visual_style}));
  }
  const payload = () => ({...options, channel_id: channelId, avatar_id: options.avatar_id || null,
    music_path: options.music_path || null, narration_path: options.narration_path || null});
  async function upload(file: File | undefined, kind: string, assign: (path: string) => void) {
    if (!file) return;
    await work(async () => {
      const result = await request<{path:string}>(`/studio/uploads/${kind}`, {method:"POST", headers:{"X-Filename":encodeURIComponent(file.name), "Content-Type":"application/octet-stream"}, body:file});
      assign(result.path); setNotice(`${file.name} is ready.`);
    });
  }
  async function saveDraft() {
    const saved = await request<{project:Production;review:Review}>("/studio/productions", {method:"POST",body:JSON.stringify(payload())});
    setDraftId(saved.project.id); setReview(saved.review); await refresh(); return saved.project.id;
  }
  async function createChannel(event: FormEvent) {
    event.preventDefault(); await work(async () => {
      const c = await request<Channel>("/channels", {method:"POST",body:JSON.stringify({name:channelName,style_preset:"documentary",settings_json:{niche,visual_style:brand}})});
      await refresh(); setChannelId(c.id); setChannelName(""); setNiche(""); setOptions(old => ({...old,avatar_id:"",visual_style:brand}));
      setReview(null); setDraftId(null); setTab("characters"); setNotice("Channel created. Add its first character, or create a visual-only video.");
    });
  }
  async function saveCharacter(event: FormEvent) {
    event.preventDefault(); await work(async () => {
      const body = {channel_id:channelId,name:character.name,presenter_provider:character.presenter_provider,
        provider_avatar_id:character.provider_avatar_id || null,reference_image_path:character.reference_image_path || null,
        voice_provider:character.voice_provider,voice_id:character.voice_id || null,
        settings_json:{persona:character.persona,language:character.language,appearance:character.appearance,
          consent_confirmed:character.consent,higgsfield_motion_prompt:`${character.persona}. Natural blinking, subtle head motion, stable camera, synchronized speech.`}};
      await request(editingCharacter ? `/studio/characters/${editingCharacter}` : "/avatars", {method:editingCharacter ? "PUT" : "POST",body:JSON.stringify(body)});
      await refresh(); setCharacter(blankCharacter); setEditingCharacter(null); setNotice("Character saved with its voice and persona.");
    });
  }
  const channel = data?.channels.find(c => c.id === channelId);
  const characters = data?.characters.filter(c => c.channel_id === channelId) || [];
  const projects = data?.projects.filter(p => p.channel_id === channelId && p.production_json?.script) || [];
  const wordCount = options.script.trim().split(/\s+/).filter(Boolean).length;
  async function previewVoice() {
    if (!options.script.trim()) return;
    await work(async () => {
      const c = characters.find(item => item.id === options.avatar_id);
      if (!c?.voice_provider) throw new Error("Choose a character with a configured voice first");
      const result = await request<{preview_url:string}>("/studio/commercial/voice-preview", {method:"POST", body:JSON.stringify({text: options.script.slice(0, 650), provider:c.voice_provider, voice_id:c.voice_id || null})});
      setVoicePreviewUrl(`http://127.0.0.1:8765${result.preview_url}`); setNotice("Voice preview ready. Review pacing before production.");
    });
  }
  async function assistDirection() {
    if (!options.script.trim()) return;
    setDirectionBusy(true); setError("");
    try {
      const result = await request<{scenes:{direction:string}[]}>("/studio/commercial/scene-direction", {method:"POST", body:JSON.stringify({script:options.script, visual_style:options.visual_style, scene_seconds:options.scene_seconds})});
      const direction = result.scenes.map((scene, index) => `Scene ${index + 1}: ${scene.direction}`).join("\n");
      change("visual_style", direction); setNotice("Scene direction suggested. Review it before saving.");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not suggest scene direction"); }
    finally { setDirectionBusy(false); }
  }
  async function recommendMusic() {
    await work(async () => {
      const result = await request<{selected:string|null;note:string}>(`/studio/commercial/music/recommend?mood=${encodeURIComponent(options.music_mood)}`);
      if (result.selected) { change("music_path", result.selected); change("music_strategy", "automatic"); }
      setNotice(result.note);
    });
  }

  return <div className="channel-studio">
    <header className="cs-hero"><div><span className="cs-eyebrow">AIVATAR / CHANNEL STUDIO</span><h1>Your character. Every story.</h1><p>Build a recurring host, drop in a script, and produce a complete video.</p></div><span className="cs-local">Local workspace</span></header>
    <div className="cs-toolbar"><div className="cs-toolbar-select"><BaseSelect label="Channel" ariaLabel="Active channel" value={channelId} onChange={chooseChannel} options={[{value:"",label:"Choose a channel"}, ...(data?.channels.map(c => ({value:c.id,label:c.name})) || [])]} /></div><BaseButton type="button" className="btn secondary" onClick={() => setTab("channels")}>+ New channel</BaseButton><div className="cs-usage"><b>{data?.usage.finished_minutes ?? 0} min</b><span>finished · {data?.usage.concurrent_projects ?? "—"} concurrent jobs</span></div></div>
    <BaseTabs value={tab} onChange={setTab} items={[["create","Create video"],["characters",<>Characters<small>{characters.length}</small></>],["productions","Productions"],["channels","Channels"]].map(([value,label]) => ({value: String(value), label}))} />
    {error && <div className="cs-alert error" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError("")}>×</button></div>}
    {notice && <div className="cs-alert" role="status">{notice}</div>}
    {!data && !error && <p role="status">Connecting to your studio…</p>}
    {!channelId && tab !== "channels" && <div className="cs-empty"><h2>Start with a channel</h2><p>Each channel keeps its own characters, visual style and productions.</p><button className="btn" onClick={() => setTab("channels")}>Create your first channel</button></div>}
    {tab === "channels" && <div className="cs-columns"><form className="cs-card" onSubmit={createChannel}><span className="cs-step">01 / WORKSPACE</span><h2>A home for your next series</h2><label>Channel name<input required maxLength={160} value={channelName} onChange={e => setChannelName(e.target.value)} placeholder="e.g. Everyday Discoveries" /></label><label>Niche / audience<input value={niche} onChange={e => setNiche(e.target.value)} placeholder="Science stories for curious people" /></label><label>Default visual style<textarea value={brand} onChange={e => setBrand(e.target.value)} /></label><BaseButton type="submit" className="btn" disabled={busy}>Create channel</BaseButton></form><section className="cs-card"><h2>Your channels</h2>{data?.channels.map(c => <button className="cs-list-item" key={c.id} onClick={() => {chooseChannel(c.id);setTab("create");}}><span><b>{c.name}</b><small>{c.settings_json.niche || c.style_preset}</small></span><span>Open →</span></button>)}<div className="cs-commercial"><h3>Commercial controls</h3><div className="cs-commercial-stats"><b>{data?.commercial?.credits ?? 0} credits</b><span>{data?.commercial?.subscription?.plan || "free"} plan</span><span>{data?.commercial?.members?.length || 0} member{data?.commercial?.members?.length === 1 ? "" : "s"}</span></div><p className="cs-muted">Voice previews, automatic music, transitions and scene direction are active. Team roles and Stripe checkout become active after hosted auth and Stripe keys are configured.</p></div></section></div>}
    {tab === "characters" && channelId && <div className="cs-columns"><form className="cs-card" onSubmit={saveCharacter}><span className="cs-step">02 / CAST YOUR CHARACTER</span><h2>{editingCharacter ? "Edit character" : "A familiar face. A consistent voice."}</h2><label>Character name<input required value={character.name} onChange={e => setCharacter({...character,name:e.target.value})} placeholder="e.g. Kristen — Documentary Host" /></label><BaseSelect label="Presenter service" value={character.presenter_provider} onChange={value => setCharacter({...character,presenter_provider:value})} options={[{value:"authorized_higgsfield",label:"Higgsfield · reference image"},{value:"authorized_heygen",label:"HeyGen · account avatar"}]} />
      {character.presenter_provider === "authorized_heygen" ? <label>HeyGen avatar ID<input required value={character.provider_avatar_id} onChange={e => setCharacter({...character,provider_avatar_id:e.target.value})} placeholder="Use a verified avatar ID from your account" /></label> : <><label>Reference image<input type="file" accept="image/png,image/jpeg,image/webp" disabled={busy} onChange={e => void upload(e.target.files?.[0],"image",path => setCharacter(old => ({...old,reference_image_path:path})))} /></label>{character.reference_image_path && <p className="cs-file">Reference image saved ✓</p>}<label>Appearance prompt<textarea value={character.appearance} onChange={e => setCharacter({...character,appearance:e.target.value})} placeholder="An original adult presenter, front-facing portrait, soft studio light…" /></label><button type="button" className="btn secondary" disabled={busy || !character.appearance.trim()} onClick={() => void work(async () => {const r = await request<{path:string}>("/studio/character-image",{method:"POST",body:JSON.stringify({prompt:character.appearance,approved:true})});setCharacter(old => ({...old,reference_image_path:r.path}));setNotice("Character image generated and saved. Generation uses your configured image provider.");})}>Generate face · uses provider credits</button></>}
      <div className="cs-field-row"><BaseSelect label="Voice service" value={character.voice_provider} onChange={value => setCharacter({...character,voice_provider:value})} options={[{value:"ai33",label:"AI33"},{value:"69labs",label:"69Labs"}]} /><label>Voice ID<input value={character.voice_id} onChange={e => setCharacter({...character,voice_id:e.target.value})} placeholder="Provider voice ID" /></label></div><label>Persona / delivery<textarea value={character.persona} onChange={e => setCharacter({...character,persona:e.target.value})} /></label><label>Language label<input value={character.language} onChange={e => setCharacter({...character,language:e.target.value})} /></label><p className="cs-muted">Choose a voice that supports your script’s language. The language label documents your character; it does not translate speech.</p><BaseCheckbox required checked={character.consent} onChange={consent => setCharacter({...character,consent})}>I have permission to use this character’s likeness and voice.</BaseCheckbox><BaseButton type="submit" className="btn" disabled={busy}>Save character</BaseButton>{editingCharacter && <button className="btn secondary" type="button" onClick={() => {setEditingCharacter(null);setCharacter(blankCharacter);}}>Cancel edit</button>}</form>
      <section className="cs-card"><h2>Cast of {channel?.name}</h2>{characters.length === 0 && <p className="cs-muted">Save a character once and reuse it across every episode.</p>}{characters.map(c => <article className="cs-character" key={c.id}><div className="cs-avatar">{c.reference_image_path ? <img src={`http://127.0.0.1:8765/studio/characters/${c.id}/image`} alt={c.name} /> : c.name.slice(0,1)}</div><div><h3>{c.name}</h3><p>{c.settings_json.persona || "No persona set"}</p><small>{c.settings_json.language || "Language not set"} · {c.presenter_provider === "authorized_heygen" ? "HeyGen" : "Higgsfield"}</small><div className="cs-actions"><button className="btn secondary" onClick={() => {change("avatar_id",c.id);setTab("create");}}>Use character</button><button className="cs-link" onClick={() => {setEditingCharacter(c.id);setCharacter({name:c.name,presenter_provider:c.presenter_provider,provider_avatar_id:c.provider_avatar_id || "",reference_image_path:c.reference_image_path || "",voice_provider:c.voice_provider,voice_id:c.voice_id || "",persona:c.settings_json.persona || "",language:c.settings_json.language || "English",appearance:c.settings_json.appearance || "",consent:!!c.settings_json.consent_confirmed});}}>Edit</button></div></div></article>)}</section></div>}
    {tab === "create" && channelId && <div className="cs-columns"><section className="cs-card"><span className="cs-step">03 / TELL YOUR STORY</span><h2>From script to finished video</h2><label>Video title<input value={options.name} onChange={e => change("name",e.target.value)} placeholder="Give this episode a name" /></label><BaseSelect label="Character" value={options.avatar_id} onChange={value => change("avatar_id",value)} options={[{value:"",label:"No character / visual-only"},...characters.map(c => ({value:c.id,label:c.name}))]} /><label>Script<textarea className="cs-script" value={options.script} onChange={e => change("script",e.target.value)} placeholder="Paste the complete narration. Your words are preserved." /></label><div className="cs-script-meta"><span>{wordCount} words · ≈ {seconds(wordCount / options.words_per_minute * 60)}</span><label className="cs-import">Import .txt<input type="file" accept=".txt,text/plain" onChange={e => {const file=e.target.files?.[0];if(file) void file.text().then(text => change("script",text));}} /></label></div>
      <div className="cs-field-row"><BaseSelect label="Format" value={options.aspect_ratio} onChange={value => change("aspect_ratio",value)} options={["16:9","9:16","1:1","4:5"].map(value => ({value,label:value}))} /><BaseSelect label="Resolution" value={options.resolution} onChange={value => change("resolution",value)} options={[{value:"1080p",label:"1080p"},{value:"720p",label:"720p"}]} /></div><label>Visual direction<textarea value={options.visual_style} onChange={e => change("visual_style",e.target.value)} /></label><div className="cs-actions"><button type="button" className="btn secondary" disabled={directionBusy || !options.script.trim()} onClick={() => void assistDirection()}>{directionBusy ? "Suggesting…" : "Suggest scene direction"}</button></div><label>Presenter coverage · {Math.round(options.presenter_target*100)}%<BaseSlider ariaLabel="Presenter coverage" min={0} max={1} step={.1} value={options.presenter_target} onChange={value => change("presenter_target",value)} /></label><p className="cs-muted">Use 0% for faceless videos. Short scripts may round up to one presenter scene.</p>
      <BaseAccordion title="Audio, captions, music and pacing"><div className="cs-field-row"><label>Words per minute<input type="number" min={80} max={220} value={options.words_per_minute} onChange={e => change("words_per_minute",Number(e.target.value))} /></label><label>Target scene length<input type="number" min={5} max={15} value={options.scene_seconds} onChange={e => change("scene_seconds",Number(e.target.value))} /></label></div><div className="cs-actions"><button type="button" className="btn secondary" disabled={busy || !options.avatar_id || !options.script.trim()} onClick={() => void previewVoice()}>Preview selected voice</button>{voicePreviewUrl && <audio controls src={voicePreviewUrl} />}</div><label>Narration audio (optional)<input type="file" accept=".mp3,.wav,.m4a" disabled={busy} onChange={e => void upload(e.target.files?.[0],"narration",path => change("narration_path",path))} /></label>{options.narration_path && <button className="cs-link" onClick={() => change("narration_path","")}>Remove uploaded narration</button>}<div className="cs-field-row"><BaseSelect label="Music mode" value={options.music_strategy} onChange={value => change("music_strategy",value)} options={[{value:"off",label:"Off"},{value:"automatic",label:"Automatic local catalog"},{value:"uploaded",label:"Uploaded track"}]} /><label>Mood<input value={options.music_mood} onChange={e => change("music_mood",e.target.value)} /></label></div><div className="cs-actions"><button type="button" className="btn secondary" disabled={busy} onClick={() => void recommendMusic()}>Choose ambient music</button></div><label>Background music (optional)<input type="file" accept=".mp3,.wav,.m4a" disabled={busy} onChange={e => void upload(e.target.files?.[0],"music",path => change("music_path",path))} /></label>{options.music_path && <button className="cs-link" onClick={() => change("music_path","")}>Remove music</button>}<p className="cs-muted">Automatic selection only uses tracks in the licensed local music catalog. Music is ducked during speech.</p><label>Music level · {Math.round(options.music_volume*100)}%<BaseSlider ariaLabel="Music level" min={0} max={.4} step={.01} value={options.music_volume} onChange={value => change("music_volume",value)} /></label><BaseSelect label="Transitions" value={options.transition_style} onChange={value => change("transition_style",value)} options={[{value:"crossfade",label:"Smooth crossfade"},{value:"fade",label:"Fade"},{value:"wipeleft",label:"Wipe left"},{value:"slideright",label:"Slide right"},{value:"cut",label:"Hard cut"}]} /><BaseCheckbox checked={options.captions} onChange={checked => change("captions",checked)}>Burn captions into video</BaseCheckbox><div className="cs-field-row"><label>Caption size<input type="number" min={14} max={40} value={options.caption_size} onChange={e => change("caption_size",Number(e.target.value))} /></label><label>Split-layout background<input type="color" value={options.background_color} onChange={e => change("background_color",e.target.value)} /></label></div></BaseAccordion>
      <div className="cs-field-row"><label>Planning budget (USD)<input type="number" min={1} max={1000} value={options.budget_usd} onChange={e => change("budget_usd",Number(e.target.value))} /></label><BaseSelect label="Generation mode" value={options.mode} onChange={value => change("mode",value)} options={[{value:"production",label:"Production · paid providers"},{value:"demo",label:"Demo · test patterns and tone"}]} /></div><div className="cs-actions"><BaseButton type="button" className="btn" disabled={busy || !options.script.trim() || !options.name.trim()} onClick={() => void work(async () => {setReview(await request<Review>("/studio/plan",{method:"POST",body:JSON.stringify(payload())}));setApproved(false);})}>{busy ? "Working…" : "Review production →"}</BaseButton><button className="btn secondary" disabled={busy || !options.script.trim() || !options.name.trim()} onClick={() => void work(async () => {await saveDraft();setNotice("Draft saved. No generation has started.");})}>Save draft</button></div></section>
      <section className="cs-card cs-review"><span className="cs-step">04 / REVIEW & GENERATE</span><h2>The production plan</h2>{!review ? <div className="cs-empty"><div className="cs-orbit">✦</div><h3>Your story, planned automatically</h3><p>Review timing, scene layouts and provider readiness before starting a render.</p><ol><li>Narration in your selected voice</li><li>Presenter and supporting visuals</li><li>Music, captions and MP4 export</li></ol></div> : <><div className="cs-stat-row"><div><b>{seconds(review.duration)}</b><small>estimated runtime</small></div><div><b>{review.scenes.length}</b><small>planned scenes</small></div><div><b>${review.presenter_guard_estimate_usd.toFixed(2)}</b><small>presenter guard estimate</small></div></div><p className="cs-muted">{review.cost_note}</p>{review.blockers.length > 0 && <div className="cs-blockers"><b>Setup needed before production</b><ul>{review.blockers.map(s => <li key={s}>{s}</li>)}</ul></div>}{review.warnings.map(s => <p className="cs-muted" key={s}>{s}</p>)}<div className="cs-scenes">{review.scenes.map(s => <article key={s.ordinal}><span className="cs-scene-number">{String(s.ordinal).padStart(2,"0")}</span><div><small>{s.type.replaceAll("_"," ")} · {seconds(s.start)}–{seconds(s.end)}</small><p>{s.narration}</p></div></article>)}</div><p className="cs-muted">{review.timing_note}</p><BaseCheckbox checked={approved} onChange={setApproved}>I approve this script and the selected providers’ generation charges{options.mode === "demo" ? " (demo has no provider calls)" : ""}.</BaseCheckbox><button className="btn cs-generate" disabled={busy || !approved || !review.ready} onClick={() => void work(async () => {const id=draftId || await saveDraft();await request(`/studio/productions/${id}/generate`,{method:"POST",body:JSON.stringify({approved:true})});await refresh();setTab("productions");setDraftId(null);setApproved(false);setNotice("Production queued. Progress is saved automatically.");})}>Approve & generate video</button></>}</section></div>}
    {tab === "productions" && channelId && <section className="cs-card"><div className="cs-section-heading"><div><h2>Productions</h2><p>Saved drafts and render progress for {channel?.name}.</p></div><button className="btn secondary" disabled={busy} onClick={() => void work(async () => {await refresh();})}>Refresh</button></div>{projects.length === 0 && <div className="cs-empty"><h3>Your next video starts here</h3><p>Save a script or generate a production to see it here.</p><button className="btn" onClick={() => setTab("create")}>Create video</button></div>}{projects.map(p => {const job=data?.jobs.find(j => j.project_id === p.id); const active=job && ["RUNNING","QUEUED"].includes(job.state);return <article className="cs-production" key={p.id}><div className="cs-section-heading"><div><h3>{p.name}</h3><small>{p.production_json.mode === "demo" ? "DEMO · " : ""}{seconds(p.final_duration || p.expected_duration)} · {p.production_json.aspect_ratio} · {p.production_json.resolution}</small></div><span className={`cs-status ${p.state === "COMPLETED" ? "done" : ""}`}>{job?.state || p.state}</span></div>{job && <><progress value={job.progress} max={1} aria-label={`${p.name} progress`} /><p className="cs-muted">{job.payload_json.stage || job.state}{active && " · You can leave this page while the API remains running."}</p></>}{(job?.error || p.error) && <p className="cs-job-error">{job?.error || p.error}</p>}<div className="cs-actions">{p.state === "COMPLETED" && <><button className="btn" onClick={() => {setSelected(p);setDetail(null);}}>Preview</button><a className="btn secondary" href={exportUrl(p.id,"video")} download>Download MP4</a><a className="cs-link" href={exportUrl(p.id,"captions")} download>Captions</a><a className="cs-link" href={exportUrl(p.id,"plan")} download>Scene plan</a></>}{!active && p.state !== "COMPLETED" && <button className="btn secondary" onClick={() => {setOptions({...initialOptions,...p.production_json,avatar_id:p.production_json.avatar_id || "",music_path:p.production_json.music_path || "",narration_path:p.production_json.narration_path || ""});setDraftId(p.id);setReview(null);setApproved(false);setTab("create");}}>Review / continue</button>}{active && <button className="cs-link" disabled={busy} onClick={() => void work(async () => {await request(`/jobs/${job.id}/cancel`,{method:"POST"});await refresh();setNotice("Cancellation requested. An in-flight provider request may finish before the job stops.");})}>Cancel at next stage</button>}</div></article>;})}<p className="cs-muted">Reported provider cost: ${data?.usage.reported_cost_usd.toFixed(2)}. {data?.usage.cost_note}</p></section>}
    {selected && <div className="cs-modal" role="dialog" aria-modal="true" aria-label="Video preview"><div className="cs-card"><div className="cs-section-heading"><h2>{selected.name}</h2><button className="btn secondary" onClick={() => setSelected(null)}>Close</button></div><video src={exportUrl(selected.id,"video")} controls /><p className="cs-muted">{detail?.renders?.[0]?.qc_json?.mode === "demo" ? "Demo output: test media only." : "Review lip sync, captions and visual consistency before publishing."}</p><a className="btn" href={exportUrl(selected.id,"video")} download>Download MP4</a></div></div>}
  </div>;
}

