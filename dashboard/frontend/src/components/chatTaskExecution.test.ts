import { afterEach, describe, expect, it, vi } from 'vitest'

import { runPlaygroundTask } from './chatTaskExecution'
import type { Message, PlaygroundTask } from './ChatComponentTypes'
import type { ToolDefinition } from '../tools'

const probeTool: ToolDefinition = {
  type: 'function',
  function: {
    name: 'lookup_policy',
    description: 'Look up a policy.',
    parameters: { type: 'object', properties: {}, required: [] },
  },
}

describe('runPlaygroundTask', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends the server materialized probe request without injecting or executing tools', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          choices: [
            {
              index: 0,
              message: {
                content: null,
                tool_calls: [
                  {
                    id: 'call-1',
                    type: 'function',
                    function: { name: 'lookup_policy', arguments: '{}' },
                  },
                ],
              },
            },
          ],
        }),
        { headers: { 'content-type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    const task: PlaygroundTask = {
      id: 'task-1',
      conversationId: 'conversation-1',
      prompt: 'Check the policy.',
      createdAt: 1,
      requestOptions: {
        enableClawMode: false,
        enableWebSearch: false,
        executeToolCalls: false,
        model: 'vllm-sr/mom-balanced-v1',
      },
      exactRequest: {
        model: 'vllm-sr/mom-balanced-v1',
        messages: [{ role: 'user', content: 'Check the policy.' }],
        tools: [probeTool],
        temperature: 0,
      },
    }
    const buildTaskTools = vi.fn(() => [probeTool])
    const executeTools = vi.fn(async () => [])
    let messages: Message[] = []
    let nextId = 0

    await runPlaygroundTask({
      buildTaskTools,
      clawManagementDisabled: false,
      clearConversationActiveTask: vi.fn(),
      endpoint: '/api/router/v1/chat/completions',
      executeTools,
      expandedToolCardCount: 0,
      generateId: () => `message-${nextId++}`,
      getConversationMessagesSnapshot: () => messages,
      getCurrentConversationId: () => 'conversation-1',
      registerAbortController: vi.fn(),
      setConversationError: vi.fn(),
      setConversationHeaderReveal: vi.fn(),
      setConversationThinking: vi.fn(),
      setExpandedToolCards: vi.fn(),
      task,
      updateConversationMessages: (_conversationId, updater) => {
        messages = updater(messages)
      },
    })

    expect(buildTaskTools).not.toHaveBeenCalled()
    expect(executeTools).not.toHaveBeenCalled()
    expect(fetchMock).toHaveBeenCalledOnce()
    const [, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(String(requestInit.body))).toEqual({
      model: 'vllm-sr/mom-balanced-v1',
      messages: [{ role: 'user', content: 'Check the policy.' }],
      tools: [probeTool],
      temperature: 0,
      stream: true,
      max_completion_tokens: 2048,
    })
    expect(requestInit.headers).toMatchObject({ 'x-session-id': 'conversation-1' })
    expect(messages[messages.length - 1]).toMatchObject({
      role: 'assistant',
      isStreaming: false,
      toolCalls: [{ status: 'skipped' }],
    })
  })

  it('preserves a streamed follow-up answer when the initial tool stream finishes within one frame', async () => {
    const encoder = new TextEncoder()
    const streamResponse = (chunks: string[]) =>
      new Response(
        new ReadableStream({
          start(controller) {
            chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)))
            controller.close()
          },
        }),
        { headers: { 'content-type': 'text/event-stream' } },
      )
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        streamResponse([
          'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"call-1","type":"function","function":{"name":"lookup_policy","arguments":"{}"}}]}}]}\n\n',
          'data: {"choices":[{"index":0,"finish_reason":"tool_calls"}]}\n\n',
          'data: [DONE]\n\n',
        ]),
      )
      .mockResolvedValueOnce(
        streamResponse([
          'data: {"choices":[{"index":0,"delta":{"content":"Policy found."}}]}\n\n',
          'data: [DONE]\n\n',
        ]),
      )
    vi.stubGlobal('fetch', fetchMock)

    const task: PlaygroundTask = {
      id: 'task-tool-loop',
      conversationId: 'conversation-tool-loop',
      prompt: 'Check the policy.',
      createdAt: 1,
      requestOptions: {
        enableClawMode: false,
        enableWebSearch: false,
        model: 'vllm-sr/auto',
      },
    }
    let messages: Message[] = []
    let nextId = 0

    await runPlaygroundTask({
      buildTaskTools: () => [probeTool],
      clawManagementDisabled: false,
      clearConversationActiveTask: vi.fn(),
      endpoint: '/api/router/v1/chat/completions',
      executeTools: vi.fn(async () => [
        { callId: 'call-1', name: 'lookup_policy', content: { found: true } },
      ]),
      expandedToolCardCount: 0,
      generateId: () => `message-${nextId++}`,
      getConversationMessagesSnapshot: () => messages,
      getCurrentConversationId: () => 'conversation-tool-loop',
      registerAbortController: vi.fn(),
      setConversationError: vi.fn(),
      setConversationHeaderReveal: vi.fn(),
      setConversationThinking: vi.fn(),
      setExpandedToolCards: vi.fn(),
      task,
      updateConversationMessages: (_conversationId, updater) => {
        messages = updater(messages)
      },
    })

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(messages[messages.length - 1]).toMatchObject({
      role: 'assistant',
      content: 'Policy found.',
      isStreaming: false,
      toolCalls: [{ id: 'call-1', status: 'completed' }],
    })
  })
})
