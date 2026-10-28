import type { AnalysisResult, AlternativeGeneration, Language } from './api'

export type GeneratedAnalyzer = (language: Language['id'], source: string) => Promise<AnalysisResult>

export function analyzeGeneratedAlternative(
  generated: AlternativeGeneration,
  analyze: GeneratedAnalyzer,
): Promise<AnalysisResult> {
  return analyze(generated.language, generated.generated_code)
}
