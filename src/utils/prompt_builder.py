# =============================================================================
# GEMINI PROMPT BUILDER
# =============================================================================
# Creates optimized prompts for Google Gemini API translation requests

class PromptBuilder:
    def __init__(self):
        self.base_template = """You are a professional translator specializing in social media content. Translate the following English tweet to {target_language}, maintaining the original tone, style, and intent.

Requirements:
- Keep the same conversational tone and personality
- Preserve all hashtags, @mentions, and URLs exactly as they appear (including placeholders like {{URL_0}}, {{MENTION_0}}, {{HASHTAG_0}})
- Maintain the tweet's character count efficiency for the target platform
- Adapt cultural references appropriately for {target_language} speakers
- If the tweet contains slang or informal language, use equivalent expressions in the target language
- Do not add explanations or additional context
- Keep the translation concise and Twitter-appropriate

Original tweet: "{tweet_content}"

Translate to {target_language}:"""
    
    def build_translation_prompt(self, tweet_text: str, target_language: str, language_config: dict = None) -> str:
        """Build translation prompt for Gemini API"""
        prompt = self.base_template.format(
            target_language=target_language,
            tweet_content=tweet_text
        )
        
        # Add language-specific instructions if available
        if language_config:
            additional_instructions = []
            
            if not language_config.get('formal_tone', False):
                additional_instructions.append("- Use casual/informal tone appropriate for social media")
            else:
                additional_instructions.append("- Use polite/formal tone")
            
            if language_config.get('cultural_adaptation', True):
                additional_instructions.append(f"- Adapt cultural references for {target_language} speakers when possible")
            
            if additional_instructions:
                # Insert additional instructions before the original tweet
                insert_point = prompt.find('Original tweet:')
                additional_text = '\n' + '\n'.join(additional_instructions) + '\n\n'
                prompt = prompt[:insert_point] + additional_text + prompt[insert_point:]
        
        return prompt
    
    def build_shortening_prompt(self, original_text: str, current_translation: str, target_language: str, char_limit: int = 280) -> str:
        """Build prompt to shorten a translation that exceeds character limit"""
        return f"""The following translation is too long for Twitter. Please provide a shorter version that maintains the core meaning and tone:

Original English: "{original_text}"
Current translation: "{current_translation}"
Target language: {target_language}
Character limit: {char_limit}

Provide a shortened translation that fits within {char_limit} characters:"""

# Global prompt builder instance
prompt_builder = PromptBuilder()