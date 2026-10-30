import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Composer } from './Composer'

class FakeSpeechRecognition {
  static instances: FakeSpeechRecognition[] = []
  continuous = false
  interimResults = false
  lang = ''
  onstart?: () => void
  onend?: () => void
  onresult?: (event: any) => void
  onerror?: (event: any) => void
  start = vi.fn(() => this.onstart?.())
  stop = vi.fn(() => this.onend?.())

  constructor() { FakeSpeechRecognition.instances.push(this) }
}

describe('hands-free voice composer', () => {
  afterEach(() => {
    FakeSpeechRecognition.instances = []
    vi.restoreAllMocks()
  })

  it('starts listening once, transcribes speech, and sends without a send-button click', async () => {
    Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: FakeSpeechRecognition })
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }) },
    })
    const onVoiceSend = vi.fn()
    const onVoiceModeChange = vi.fn()
    const props = {
      onSend: vi.fn(),
      onVoiceSend,
      streaming: false,
      onStop: vi.fn(),
      voicePaused: false,
      onVoiceModeChange,
    }
    const view = render(<Composer {...props} voiceMode={false} />)

    fireEvent.click(screen.getByRole('button', { name: 'Turn on hands-free voice mode' }))
    await waitFor(() => expect(onVoiceModeChange).toHaveBeenCalledWith(true))

    // Parent flips the mode after the permission gesture, just as ChatShell does.
    view.rerender(<Composer {...props} voiceMode />)
    await waitFor(() => expect(FakeSpeechRecognition.instances).toHaveLength(1))
    const recognition = FakeSpeechRecognition.instances[0]
    await waitFor(() => expect(recognition.start).toHaveBeenCalled())
    recognition.onresult?.({
      resultIndex: 0,
      results: Object.assign([{ 0: { transcript: 'Open Calculator' }, isFinal: true }], { length: 1 }),
    })
    await waitFor(() => expect(onVoiceSend).toHaveBeenCalledWith('Open Calculator'), { timeout: 2500 })
  })
})
