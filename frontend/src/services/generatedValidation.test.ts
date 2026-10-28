import { describe, expect, it, vi } from 'vitest'
import { analyzeGeneratedAlternative } from './generatedValidation'

describe('generated alternative validation', () => {
  it('submits generated source independently using the generated language', async () => {
    const analysis = {
      language: 'mini_cpp',
      grammar_version: 'mini-cpp-1.0',
      lexical_valid: true,
      syntax_valid: true,
      success: true,
      tokens: [],
      diagnostics: [],
      tree: null,
      parse_status: 'valid_complete' as const,
      tree_complete: true,
      summary: { token_count: 0, diagnostic_count: 0 },
    }
    const analyze = vi.fn().mockResolvedValue(analysis)
    const generated = {
      language: 'mini_cpp' as const,
      generated_code: 'int main() { return 0; }',
      provider: 'groq' as const,
      model: 'openai/gpt-oss-20b',
    }

    await expect(analyzeGeneratedAlternative(generated, analyze)).resolves.toBe(analysis)
    expect(analyze).toHaveBeenCalledOnce()
    expect(analyze).toHaveBeenCalledWith('mini_cpp', generated.generated_code)
  })
})
