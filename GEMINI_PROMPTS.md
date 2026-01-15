# Gemini Translation Prompts
# ===========================
# Updated from Claude to Gemini by: AI Assistant on 2025-01-18
# Purpose: Document effective prompting strategies for Google Gemini AI in translation tasks

## Overview

This document contains optimized prompts for Google Gemini AI to achieve high-quality, context-aware translations of social media content, specifically Twitter tweets.

## Base Translation Prompt

### Core Prompt Template
```
You are a professional translator specializing in social media content. Translate the following English tweet to {target_language}, maintaining the original tone, style, and intent.

Requirements:
- Keep the same conversational tone and personality
- Preserve all hashtags, @mentions, and URLs exactly as they appear (including placeholders like {URL_0}, {MENTION_0}, {HASHTAG_0})
- Maintain the tweet's character count efficiency for the target platform
- Adapt cultural references appropriately for {target_language} speakers
- If the tweet contains slang or informal language, use equivalent expressions in the target language
- Do not add explanations or additional context
- Keep the translation concise and Twitter-appropriate

Original tweet: "{tweet_content}"

Translate to {target_language}:
```

## Gemini-Specific Optimizations

### Tone Control
Gemini responds well to clear personality instructions:

**For Casual Tone:**
```
Use casual, friendly language that sounds natural on social media. Avoid overly formal or academic phrasing.
```

**For Professional Tone:**
```
Maintain a professional but approachable tone. Use polite language appropriate for business social media.
```

### Cultural Adaptation Instructions
```
- Adapt cultural references for {target_language} speakers when possible
- If a cultural reference cannot be adapted, preserve it but ensure it's understandable
- Use culturally appropriate expressions and idioms when they exist
- Consider local social media conventions and hashtag practices
```

## Language-Specific Prompts

### Japanese Translation
```
Additional instructions for Japanese:
- Use casual/polite form appropriate for social media (avoid keigo unless specifically needed)
- Consider character efficiency - Japanese can often express ideas more concisely
- Preserve the original tweet's energy and emotion
- Use appropriate particles and sentence endings for social media context
```

### Spanish Translation
```
Additional instructions for Spanish:
- Use neutral Spanish unless targeting a specific region
- Maintain the informal "tú" form for social media context
- Preserve exclamation points and emotional punctuation
- Consider character count - Spanish often requires more characters than English
```

### French Translation
```
Additional instructions for French:
- Use informal register appropriate for social media
- Pay attention to gender agreements in translations
- Preserve the original tweet's personality and style
- Consider French social media conventions for hashtags
```

## Advanced Prompting Techniques

### For Thread Translations
```
This tweet is part of a thread. Maintain consistency with:
- Previous translation style and tone
- Terminology choices made in earlier tweets
- Overall narrative flow and personality
```

### For Tweets with Media
```
This tweet includes media (image/video). The translation should:
- Complement the visual content
- Maintain the same relationship between text and media as the original
- Consider that the audience will see both the media and translated text
```

### For Promotional Content
```
This is promotional content. Ensure the translation:
- Maintains the marketing appeal and call-to-action effectiveness
- Adapts promotional language to target market conventions
- Preserves urgency or excitement in the messaging
```

## Common Challenges and Solutions

### Character Limit Issues
When Gemini produces translations that are too long:

```
The translation exceeds Twitter's character limit. Please provide a shorter version that maintains the core meaning and tone:

Original: "{original_text}"
Current translation: "{long_translation}"
Target language: {target_language}
Character limit: 280

Requirements:
- Keep the essential message
- Maintain the original tone
- Preserve important hashtags and mentions
- Stay within 280 characters

Shortened translation:
```

### Hashtag Handling
For better hashtag preservation:

```
Important: Hashtags serve as discovery and community markers. When translating:
- Keep hashtags in their original form when they're proper nouns or universal terms
- Only translate hashtags if they have established translated versions in the target language
- Preserve hashtag placement and spacing exactly as in the original
```

### Mention Preservation
```
@mentions refer to specific users and must never be translated or modified. Always preserve:
- Exact spelling and capitalization of usernames
- The @ symbol positioning
- Spacing around mentions
```

## Quality Control Prompts

### Self-Validation Prompt
Add this as a follow-up instruction:

```
Before providing your final translation, verify:
1. Character count is under 280
2. All @mentions and hashtags are exactly preserved
3. URLs are maintained as placeholders
4. The tone matches the original
5. The meaning is accurately conveyed

Final translation:
```

### Tone Verification
```
Rate this translation on:
- Tone consistency (1-10): Does it match the original's energy?
- Cultural appropriateness (1-10): Is it suitable for the target audience?
- Social media compatibility (1-10): Does it sound natural on Twitter?

If any score is below 8, provide an improved version.
```

## Model-Specific Settings

### Recommended Gemini Configuration
```python
generation_config = {
    "temperature": 0.3,  # Lower for more consistent translations
    "top_p": 0.8,        # Balanced creativity and accuracy
    "top_k": 40,         # Moderate vocabulary diversity
    "max_output_tokens": 1000,
    "stop_sequences": []
}
```

### Safety Settings for Translation
```python
safety_settings = [
    {
        "category": "HARM_CATEGORY_HARASSMENT",
        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
    },
    {
        "category": "HARM_CATEGORY_HATE_SPEECH", 
        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
    },
    {
        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
    },
    {
        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
    }
]
```

## Performance Optimization

### Batch Translation Prompt
For translating multiple tweets to multiple languages in one call:

```
Translate the following tweet to multiple languages. For each language, maintain consistent quality and style.

Original tweet: "{tweet_content}"

Provide translations in this JSON format:
{
  "japanese": "translation here",
  "spanish": "translation here", 
  "french": "translation here"
}

Requirements for all translations:
- Preserve all @mentions, #hashtags, and URLs exactly
- Keep under 280 characters per translation
- Maintain original tone and personality
- Adapt cultural references appropriately

Translations:
```

### Caching Strategy
Use these elements in cache keys:
- Original tweet text hash
- Target language
- Tone setting (formal/casual)
- Cultural adaptation setting (true/false)

## Testing and Validation

### Test Scenarios
Always test with:
1. **Emoji-heavy tweets** - Ensure emojis are preserved
2. **Multiple hashtags** - Verify all hashtags remain intact
3. **Mixed languages** - Handle tweets with multiple languages
4. **Long tweets** - Test character limit handling
5. **Slang/informal language** - Verify appropriate adaptation

### Quality Metrics
Track these metrics:
- Character count accuracy (within limits)
- Hashtag preservation rate (100% expected)
- Mention preservation rate (100% expected)
- URL preservation rate (100% expected)
- Cultural appropriateness rating (manual review)

## Troubleshooting

### Common Issues and Fixes

**Issue: Gemini translates hashtags**
```
Solution: Add explicit instruction: "Never translate or modify hashtags. Keep them exactly as written including capitalization."
```

**Issue: Overly formal translations**
```
Solution: Add: "Write as if you're posting on your personal social media account. Use casual, friendly language."
```

**Issue: Missing cultural context**
```
Solution: Add background: "Consider that this will be read by [target culture] social media users who may not be familiar with [source culture] references."
```

---

## Notes for Developers

- Gemini 1.5 Flash is typically sufficient for translation tasks and more cost-effective
- Gemini 1.5 Pro provides better cultural nuance understanding for complex content
- Always include fallback handling for API errors or blocked content
- Monitor token usage to optimize costs

This document should be updated as new Gemini capabilities and best practices emerge.
