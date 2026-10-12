// Everything about caption styling that the page needs, in one place.
// SIZE_PX matches the numbers render.py uses on a 1080-wide canvas, so the preview is honest.

export const CAPTION_DEFAULT = {
  enabled: true,
  style: 'outline',
  size: 'medium',
  position: 'bottom',
  color: '#FFFFFF',
  highlight: '#FFE600',
  uppercase: false,
}

export const SIZE_PX = { small: 54, medium: 66, large: 82 }
export const POSITION_OFFSET = { bottom: '19.8%', top: '13.5%' }

export const COLORS = ['#FFFFFF', '#FFE600', '#5CE1FF', '#FF6FB5', '#7CFF6B', '#FFA630']
export const HIGHLIGHT_COLORS = ['#FFE600', '#7CFF6B', '#5CE1FF', '#FF6FB5', '#FFA630', '#FFFFFF']

export const CAPTION_STYLES = [
  { id: 'outline', label: 'Outline', hint: 'Classic' },
  { id: 'box', label: 'Box', hint: 'On a dark box' },
  { id: 'karaoke', label: 'Word highlight', hint: 'Follows speech' },
]

export const SAMPLE_TEXT = {
  ta: 'இதுதான் முக்கியமான விஷயம் friends',
  hi: 'यही सबसे ज़रूरी बात है friends',
  mr: 'हीच सर्वात महत्त्वाची गोष्ट आहे friends',
  en: 'This is the one thing that matters',
}

export const LANGUAGES = [
  ['ta', 'தமிழ்', 'Tamil'],
  ['hi', 'हिन्दी', 'Hindi'],
  ['mr', 'मराठी', 'Marathi'],
  ['en', 'English', 'English'],
]
export const PLATFORMS = [
  ['reels', 'Reels', 'Instagram'],
  ['shorts', 'Shorts', 'YouTube'],
  ['tiktok', 'TikTok', 'TikTok'],
]
export const QUALITIES = [
  ['hd', 'HD 1080p', 'Sharper, takes longer'],
  ['fast', 'Fast 720p', 'About 2x quicker'],
]
export const COUNTS = [3, 5]
export const BRIEF_CHIPS = ['Funny moments', 'Best hooks', 'Tutorial steps', 'Highlight reel']

const STORAGE_KEY = 'smartix.cap'
export function loadCaption() {
  try {
    return { ...CAPTION_DEFAULT, ...(JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}) }
  } catch {
    return { ...CAPTION_DEFAULT }
  }
}
export function saveCaption(cap) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(cap)) } catch { /* private mode: fine */ }
}