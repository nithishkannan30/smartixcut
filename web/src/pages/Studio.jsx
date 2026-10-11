import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api, post, uploadVideo } from '../api'
import { loadCaption, saveCaption } from '../captionConfig'
import BriefStep from '../components/BriefStep'
import CaptionStudio from '../components/CaptionStudio'
import FormatStep from '../components/FormatStep'
import History from '../components/History'
import Progress from '../components/Progress'
import Section from '../components/Section'
import UploadStep from '../components/UploadStep'

// The builder: four steps, then "Generate clips". All the choices live here as React state.
export default function Studio() {
  const navigate = useNavigate()
  const location = useLocation()

  const [file, setFile] = useState(null)
  const [prompt, setPrompt] = useState('')
  const [language, setLanguage] = useState('ta')
  const [count, setCount] = useState(3)
  const [cap, setCap] = useState(loadCaption)
  const [platform, setPlatform] = useState('reels')
  const [quality, setQuality] = useState('hd')

  const [limits, setLimits] = useState({ maxGb: 2, maxMin: 30, maxBytes: 2 * 1024 ** 3 })
  const [problems, setProblems] = useState([])
  const [offline, setOffline] = useState(false)
  const [hint, setHint] = useState({ text: 'Choose a video to begin.', bad: false })
  const [uploading, setUploading] = useState(false)
  const [pct, setPct] = useState(0)
  const videoKey = useRef(null)       // remembered, so a retry doesn't upload the video twice
  const [startedAt, setStartedAt] = useState(0)

  useEffect(() => {
    api('/api/health')
      .then((h) => {
        setLimits({ maxGb: h.max_upload_gb, maxMin: h.max_video_minutes, maxBytes: h.max_upload_gb * 1024 ** 3 })
        setProblems(h.problems || [])
      })
      .catch(() => setOffline(true))
  }, [])

  useEffect(() => {                   // "My clips" link from another page lands here
    if (location.hash === '#history') document.getElementById('history')?.scrollIntoView()
  }, [location.hash])

  function chooseFile(f) {
    videoKey.current = null
    setFile(f)
    setHint({ text: 'Ready. Most videos take about a minute.', bad: false })
  }
  function clearFile() {
    videoKey.current = null
    setFile(null)
    setHint({ text: 'Choose a video to begin.', bad: false })
  }
  function updateCap(next) {
    setCap(next)
    saveCaption(next)
  }

  async function generate() {
    if (!file || uploading) return
    setUploading(true); setPct(0); setStartedAt(Date.now())
    try {
      if (!videoKey.current) {
        const up = await uploadVideo(file, setPct)
        videoKey.current = up.video_key
      }
      const job = await post('/api/jobs', {
        video_key: videoKey.current, prompt: prompt.trim(), language, platform,
        num_clips: count, quality, captions: cap,
      })
      navigate(`/jobs/${job.job_id}`)
    } catch (e) {
      setUploading(false)
      setHint({ text: e.message, bad: true })
    }
  }

  if (uploading) {
    return (
      <Progress status="uploading" serverProgress={2 + pct * 12} startedAt={startedAt}
        title="Making your clips…" note={`Uploading… ${Math.round(pct * 100)}%`} />
    )
  }

  return (
    <>
      <h1>Smart AI video clips in 60&nbsp;seconds</h1>
      <p className="sub">Upload a video, say what you want, and get captioned vertical clips for Reels, Shorts and TikTok in Tamil, Hindi, Marathi or English.</p>

      {offline && (
        <div className="banner">Can't reach the SmartixCut server. Start it with: uvicorn api:app --port 8000</div>
      )}
      {problems.length > 0 && (
        <div className="banner"><b>Server setup is incomplete:</b><ul>{problems.map((p) => <li key={p}>{p}</li>)}</ul></div>
      )}

      <section className="panel" id="builder">
        <Section num={1} title="Add your video">
          <UploadStep file={file} onFile={chooseFile} onClear={clearFile} limits={limits}
            onReject={(text) => setHint({ text, bad: true })} />
        </Section>
        <Section num={2} title="Say what you want">
          <BriefStep prompt={prompt} onPrompt={setPrompt} language={language} onLanguage={setLanguage}
            count={count} onCount={setCount} />
        </Section>
        <Section num={3} title="Style your captions">
          <CaptionStudio value={cap} onChange={updateCap} language={language} />
        </Section>
        <Section num={4} title="Pick a format" aside={<span className="aside">Vertical 9:16</span>}>
          <FormatStep platform={platform} onPlatform={setPlatform} quality={quality} onQuality={setQuality} />
        </Section>

        <div style={{ marginTop: 28 }}>
          <button className="btn primary" type="button" disabled={!file} onClick={generate}>Generate clips</button>
          <div className="hint" role="status" style={{ textAlign: 'center', color: hint.bad ? 'var(--bad)' : undefined }}>
            {hint.text}
          </div>
        </div>
      </section>

      <History />
    </>
  )
}
