import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, post } from '../api'
import FailureCard from '../components/FailureCard'
import Progress from '../components/Progress'
import Results from '../components/Results'

// One job. Polls the server every 1.5 s until it is done or failed.
// Because the id is in the address, a refresh (or a link from "My clips") brings you right back.
// `key={jobId}` gives every job a fresh component, so nothing from the previous job lingers.
export default function JobPage() {
  const { jobId } = useParams()
  return <JobView key={jobId} jobId={jobId} />
}

function JobView({ jobId }) {
  const navigate = useNavigate()
  const [job, setJob] = useState(null)
  const [problem, setProblem] = useState('')
  const [retryError, setRetryError] = useState('')

  useEffect(() => {
    let stopped = false
    let timer

    async function poll() {
      try {
        const j = await api(`/api/jobs/${jobId}`)
        if (stopped) return
        setJob(j)
        if (j.status !== 'done' && j.status !== 'failed') timer = setTimeout(poll, 1500)
      } catch (e) {
        if (stopped) return
        if (e.status === 404) setProblem("We couldn't find that job. It may have been deleted.")
        else timer = setTimeout(poll, 3000)       // network blip: keep trying
      }
    }
    poll()
    return () => { stopped = true; clearTimeout(timer) }
  }, [jobId])

  async function retry() {
    setRetryError('')
    try {
      const o = job.options || {}
      const next = await post('/api/jobs', {
        video_key: job.video_key, prompt: job.prompt || '', language: job.language, platform: job.platform,
        num_clips: job.num_clips, ...(o.quality ? { quality: o.quality } : {}), ...(o.captions ? { captions: o.captions } : {}),
      })
      navigate(`/jobs/${next.job_id}`)
    } catch (e) {
      setRetryError(e.message)
    }
  }

  if (problem) return <FailureCard message={problem} onNew={() => navigate('/')} />
  if (!job) return <div className="boot" role="status">Loading…</div>
  if (job.status === 'done') return <Results job={job} onNew={() => navigate('/')} />
  if (job.status === 'failed') {
    return <FailureCard message={retryError || job.error} detail={job.error_detail} onRetry={retry} onNew={() => navigate('/')} />
  }
  return <Progress status={job.status} serverProgress={job.progress} startedAt={job.created_at * 1000} />
}
