"""
Generator implementation for prompt construction and response generation.

This module handles the generation layer including prompt building,
LLM interaction, and citation extraction.
"""

import logging
import re
import json
from datetime import datetime, date
from typing import List, Optional, Dict, Any

from models import Chunk, ChatTurn, ChatResponse, Citation, AnswerBlock
from llm.base import LLMBackend

logger = logging.getLogger(__name__)


class Generator:
    """
    Generator for creating responses using retrieved chunks and LLM.
    
    This class handles:
    1. Prompt construction from context and history
    2. LLM interaction for response generation
    3. Citation extraction from chunks
    4. Response formatting
    """
    
    # Maximum number of conversation turns to include in context
    MAX_HISTORY_TURNS = 5
    
    # System prompts for different languages
    SYSTEM_PROMPTS = {
        'ja': """あなたはObsidian vaultの提供されたコンテキストに基づいて質問に答える役立つAIアシスタントです。

あなたのタスク:
1. 提供されたコンテキストのみを使用してユーザーの質問に答える
2. コンテキストに関連情報がない場合、「Vault related information that could help answer this question.」と言う
3. コンテキストに基づいて正確で役立つ回答を提供する
4. 使用した情報については[1]、[2]などの形式で引用を含める
5. 重要: 有効なJSONのみを返すこと - 他のテキストは含めない

必須JSON形式（これのみを出力）:
{
  "answer": "[1]のような引用を含む完全な回答",
  "answer_blocks": [
    {
      "type": "summary",
      "title": "簡潔な説明的タイトル",
      "content": "簡潔な内容説明",
      "items": ["具体的項目1", "具体的項目2"]
    }
  ]
}

重要:
- JSONオブジェクトのみを出力し、他には何も含めない
- 簡単化のため1つの回答ブロックのみを使用する
- コンテンツは簡潔だが情報量が豊富に保つ
- JSON値にHTMLやマークダウンを含めない
- JSONが有効で完全であることを確認する

コンテキストは番号付きチャンクとそのソース情報として提供されます。
このコンテキストのみに基づいて回答し、有効なJSONを返してください。""",
        
        'en': """You are a helpful AI assistant that answers questions based on the provided context from an Obsidian vault.

Your task is to:
1. Answer the user's question using only the information provided in the context
2. If the context doesn't contain relevant information, say "Vault related information that could help answer this question."
3. Provide accurate, helpful responses based on the context
4. Include citations for the information you use in the format [1], [2], etc.
5. CRITICAL: You MUST return your response as valid JSON only - no other text

Required JSON format (output ONLY this JSON):
{
  "answer": "Your complete answer with citations like [1]",
  "answer_blocks": [
    {
      "type": "summary",
      "title": "Brief descriptive title",
      "content": "Brief content description", 
      "items": ["specific item 1", "specific item 2"]
    }
  ]
}

IMPORTANT: 
- Output ONLY the JSON object, nothing else
- Use only one answer block for simplicity
- Keep content concise but informative
- Do not include HTML or markdown in JSON values
- Ensure JSON is valid and complete

Context will be provided as numbered chunks with their source information.
Please base your answer only on this context and return valid JSON."""
    }

    def __init__(self, llm_backend: LLMBackend):
        """
        Initialize the generator.
        
        Args:
            llm_backend: Backend for LLM generation
        """
        self.llm_backend = llm_backend
    
    def _detect_language(self, query: str) -> str:
        """
        Detect the language of the user's query.
        
        Args:
            query: User's query text
            
        Returns:
            Language code ('ja' for Japanese, 'en' for English/others)
        """
        import re
        
        # Check for Japanese characters (Hiragana, Katakana, Kanji)
        if re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', query):
            return 'ja'
        
        # Default to English for other languages
        return 'en'
    
    def _get_system_prompt(self, query: str) -> str:
        """
        Get the appropriate system prompt based on query language.
        
        Args:
            query: User's query text
            
        Returns:
            System prompt in the detected language
        """
        language = self._detect_language(query)
        return self.SYSTEM_PROMPTS.get(language, self.SYSTEM_PROMPTS['en'])
    
    
    def generate(
        self,
        query: str,
        chunks: List[Chunk],
        history: Optional[List[ChatTurn]] = None
    ) -> ChatResponse:
        """
        Generate a response based on query and retrieved chunks.
        
        Args:
            query: User's question
            chunks: Retrieved chunks for context
            history: Optional conversation history
            
        Returns:
            ChatResponse with answer and citations
            
        Raises:
            ValueError: If query is empty
            RuntimeError: If generation fails
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        
        logger.info(f"Generating response for query: '{query[:50]}...' with {len(chunks)} chunks")
        
        try:
            # Handle case with no relevant chunks
            if not chunks:
                logger.info("No relevant chunks found")
                answer = "Vault related information that could help answer this question."
                return ChatResponse(
                    answer=answer,
                    answer_blocks=[
                        AnswerBlock(type="summary", title="回答", content=answer, items=[])
                    ],
                    citations=[]
                )
            
            # Build prompt with original query
            prompt = self._build_prompt(query, chunks, history)
            
            logger.info(f"Generated prompt (length: {len(prompt)}):")
            logger.info(f"First 500 chars of prompt: {prompt[:500]}...")
            
            # Generate response from LLM
            llm_response = self.llm_backend.generate(prompt)
            
            logger.info(f"LLM response (length: {len(llm_response)}):")
            logger.info(f"LLM response: {llm_response}")
            
            # Extract answer, blocks, and citations
            answer, answer_blocks, citations = self._extract_answer_blocks_and_citations(llm_response, chunks)
            
            # Ensure citations are properly formatted
            formatted_citations = self._format_citations(citations, chunks)
            
            response = ChatResponse(answer=answer, answer_blocks=answer_blocks, citations=formatted_citations)
            
            logger.info(f"Generated response with {len(formatted_citations)} citations")
            return response
            
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise RuntimeError(f"Generation failed: {str(e)}")
    
    def _build_prompt(self, query: str, chunks: List[Chunk], history: Optional[List[ChatTurn]]) -> str:
        """
        Build prompt from query, chunks, and conversation history.
        
        Args:
            query: User's question
            chunks: Retrieved chunks for context
            history: Optional conversation history
            
        Returns:
            Complete prompt for LLM
        """
        # Get appropriate system prompt based on query language
        system_prompt = self._get_system_prompt(query)
        prompt_parts = [system_prompt]
        
        # Add context chunks
        if chunks:
            prompt_parts.append("\n--- CONTEXT ---")
            for i, chunk in enumerate(chunks, 1):
                chunk_text = self._prepare_chunk_text(chunk.text)
                prompt_parts.append(f"\nChunk {i}:\n{chunk_text}\n")
                prompt_parts.append(f"Source: {chunk.source_path} - {chunk.title}")
        
        # Add conversation history
        if history:
            prompt_parts.append("\n--- CONVERSATION HISTORY ---")
            # Take only the last MAX_HISTORY_TURNS
            recent_history = history[-self.MAX_HISTORY_TURNS:]
            for turn in recent_history:
                role_name = "User" if turn.role == "user" else "Assistant"
                prompt_parts.append(f"\n{role_name}: {turn.content}")
        
        # Add current query
        prompt_parts.append(f"\n--- CURRENT QUESTION ---")
        prompt_parts.append(f"\nUser: {query}")
        prompt_parts.append("\nAssistant:")
        
        return "\n".join(prompt_parts)
    
    def _prepare_chunk_text(self, text: str) -> str:
        """
        Prepare chunk text for inclusion in prompt.
        
        Args:
            text: Raw chunk text
            
        Returns:
            Prepared text
        """
        # Clean up text for prompt
        text = text.strip()
        
        # Limit chunk length to prevent prompt overflow
        max_chunk_length = 2000
        if len(text) > max_chunk_length:
            text = text[:max_chunk_length] + "..."
        
        return text
    
    def _extract_answer_blocks_and_citations(self, llm_response: str, chunks: List[Chunk]) -> tuple[str, List[AnswerBlock], List[Citation]]:
        """
        Extract answer, structured blocks, and citations from LLM response.
        
        Args:
            llm_response: Raw response from LLM
            chunks: Original chunks for citation mapping
            
        Returns:
            Tuple of (answer_text, answer_blocks, list_of_citations)
        """
        logger.info(f"Starting citation extraction from LLM response (length: {len(llm_response)})")
        logger.info(f"Available chunks for citation: {len(chunks)}")

        structured_output = self._parse_structured_output(llm_response)
        if structured_output:
            answer = structured_output.get("answer", "").strip()
            answer_blocks = self._build_answer_blocks(structured_output.get("answer_blocks", []), answer)
            citations = self._extract_structured_citations(answer, chunks)
            if not citations:
                citations = self._infer_citations_from_content(answer, chunks)
            return answer, answer_blocks, citations
        
        # Try to extract structured citations first
        citations = self._extract_structured_citations(llm_response, chunks)
        logger.info(f"Extracted {len(citations)} structured citations")
        
        # Clean up the response by removing citation markers
        answer = self._clean_response_text(llm_response)
        logger.info(f"Cleaned answer length: {len(answer)}")
        
        answer_blocks = [AnswerBlock(type="summary", title="回答", content=answer, items=[])]
        return answer, answer_blocks, citations

    def _parse_structured_output(self, llm_response: str) -> Optional[Dict[str, Any]]:
        """
        Parse structured JSON output from the LLM response.

        Args:
            llm_response: Raw response from the LLM

        Returns:
            Parsed dictionary or None if parsing fails
        """
        candidate = llm_response.strip()
        logger.info(f"Attempting to parse structured output from: {candidate[:200]}...")

        if candidate.startswith("```"):
            candidate = re.sub(r'^```(?:json)?\s*', '', candidate)
            candidate = re.sub(r'\s*```$', '', candidate)
            logger.info(f"After removing code blocks: {candidate[:200]}...")

        try:
            parsed = json.loads(candidate)
            logger.info("JSON parsing successful")
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parsing failed: {e}")
            logger.warning(f"Failed JSON content: {candidate}")
            return None

        if not isinstance(parsed, dict):
            logger.warning(f"Parsed JSON is not a dictionary: {type(parsed)}")
            return None

        if "answer" not in parsed:
            logger.warning(f"Parsed JSON missing 'answer' key. Keys: {list(parsed.keys())}")
            return None

        logger.info("Structured output validation successful")
        return parsed

    def _build_answer_blocks(self, raw_blocks: Any, fallback_answer: str) -> List[AnswerBlock]:
        """
        Build validated answer blocks from parsed structured output.

        Args:
            raw_blocks: Parsed raw block list
            fallback_answer: Fallback plain answer text

        Returns:
            List of AnswerBlock objects
        """
        if not isinstance(raw_blocks, list):
            return [AnswerBlock(type="summary", title="回答", content=fallback_answer, items=[])]

        answer_blocks = []
        for raw_block in raw_blocks:
            if not isinstance(raw_block, dict):
                continue

            block_type = str(raw_block.get("type", "summary"))
            title = str(raw_block.get("title", "回答"))
            content = str(raw_block.get("content", "")).strip()
            raw_items = raw_block.get("items", [])
            items = [str(item) for item in raw_items] if isinstance(raw_items, list) else []

            if not content and not items:
                continue

            answer_blocks.append(
                AnswerBlock(type=block_type, title=title, content=content, items=items)
            )

        if not answer_blocks:
            answer_blocks.append(AnswerBlock(type="summary", title="回答", content=fallback_answer, items=[]))

        return answer_blocks
    
    def _extract_structured_citations(self, response: str, chunks: List[Chunk]) -> List[Citation]:
        """
        Extract structured citations from LLM response.
        
        Args:
            response: LLM response text
            chunks: Original chunks for reference
            
        Returns:
            List of extracted citations
        """
        citations = []
        
        # Look for citation patterns like [1], [Source: note.md], etc.
        citation_patterns = [
            r'\[(\d+)\]',  # [1], [2], etc.
            r'\[Source:\s*([^\]]+)\]',  # [Source: note.md]
            r'\[([^\]]+\.md)\]',  # [note.md]
        ]
        
        for pattern in citation_patterns:
            matches = re.finditer(pattern, response, re.IGNORECASE)
            for match in matches:
                citation_ref = match.group(1)
                
                # Try to map citation to chunk
                citation = self._map_citation_to_chunk(citation_ref, chunks)
                if citation and citation not in citations:
                    citations.append(citation)
        
        # If no structured citations found, try to infer from content
        if not citations:
            citations = self._infer_citations_from_content(response, chunks)
        
        return citations
    
    def _map_citation_to_chunk(self, citation_ref: str, chunks: List[Chunk]) -> Optional[Citation]:
        """
        Map citation reference to actual chunk.
        
        Args:
            citation_ref: Citation reference (number, filename, etc.)
            chunks: Available chunks
            
        Returns:
            Citation object or None if not found
        """
        # Try numeric reference (chunk number)
        if citation_ref.isdigit():
            chunk_index = int(citation_ref) - 1  # Convert to 0-based
            if 0 <= chunk_index < len(chunks):
                return self._create_citation_from_chunk(chunks[chunk_index])
        
        # Try filename reference
        if citation_ref.endswith('.md'):
            for chunk in chunks:
                if chunk.source_path == citation_ref or chunk.source_path.endswith(citation_ref):
                    return self._create_citation_from_chunk(chunk)
        
        # Try partial filename match
        for chunk in chunks:
            if citation_ref.lower() in chunk.source_path.lower() or citation_ref.lower() in chunk.title.lower():
                return self._create_citation_from_chunk(chunk)
        
        return None
    
    def _create_citation_from_chunk(self, chunk: Chunk) -> Citation:
        """
        Create citation object from chunk.
        
        Args:
            chunk: Source chunk
            
        Returns:
            Citation object
        """
        # Extract relevant snippet (first 200 characters)
        snippet = chunk.text[:200]
        if len(chunk.text) > 200:
            snippet += "..."
        
        return Citation(
            file_path=chunk.source_path,
            title=chunk.title,
            snippet=snippet,
            source_path=chunk.source_path  # Add source_path for frontend compatibility
        )
    
    def _infer_citations_from_content(self, response: str, chunks: List[Chunk]) -> List[Citation]:
        """
        Infer citations based on content similarity.
        
        Args:
            response: LLM response
            chunks: Available chunks
            
        Returns:
            List of inferred citations
        """
        citations = []
        
        # Simple heuristic: if response contains content from a chunk, cite it
        for chunk in chunks:
            # Check if response contains significant content from chunk
            chunk_sentences = chunk.text.split('.')[:3]  # First 3 sentences
            for sentence in chunk_sentences:
                sentence = sentence.strip()
                if len(sentence) > 20 and sentence.lower() in response.lower():
                    citation = self._create_citation_from_chunk(chunk)
                    if citation not in citations:
                        citations.append(citation)
                    break
        
        return citations
    
    def _clean_response_text(self, response: str) -> str:
        """
        Clean up response text by removing citation markers.
        
        Args:
            response: Raw response from LLM
            
        Returns:
            Cleaned response text
        """
        # Remove citation markers
        response = re.sub(r'\[\d+\]', '', response)
        response = re.sub(r'\[Source:\s*[^\]]+\]', '', response)
        response = re.sub(r'\[[^\]]+\.md\]', '', response)
        
        # Clean up extra whitespace
        response = re.sub(r'\s+', ' ', response)
        response = response.strip()
        
        return response
    
    def _format_citations(self, citations: List[Citation], chunks: List[Chunk]) -> List[Citation]:
        """
        Format and validate citations.
        
        Args:
            citations: Extracted citations
            chunks: Original chunks for reference
            
        Returns:
            Formatted citations
        """
        formatted_citations = []
        
        for citation in citations:
            # Validate citation has required fields
            if not citation.file_path or not citation.title:
                continue
            
            # Ensure snippet is not too long
            if len(citation.snippet) > 300:
                citation.snippet = citation.snippet[:300] + "..."
            
            # Avoid duplicate citations
            if citation not in formatted_citations:
                formatted_citations.append(citation)
        
        return formatted_citations
    
    def get_system_prompt(self, language: str = 'en') -> str:
        """
        Get the system prompt for a specific language.
        
        Args:
            language: Language code ('ja' or 'en')
            
        Returns:
            System prompt string
        """
        return self.SYSTEM_PROMPTS.get(language, self.SYSTEM_PROMPTS['en'])
    
    def update_system_prompt(self, new_prompt: str, language: str = 'en') -> None:
        """
        Update the system prompt for a specific language.
        
        Args:
            new_prompt: New system prompt
            language: Language code ('ja' or 'en')
        """
        self.SYSTEM_PROMPTS[language] = new_prompt
        logger.info(f"Updated system prompt for language: {language}")
    
    def test_generation(self, query: str, chunks: List[Chunk]) -> Dict[str, Any]:
        """
        Test generation with detailed debugging information.
        
        Args:
            query: Test query
            chunks: Test chunks
            
        Returns:
            Dictionary with test results
        """
        try:
            # Build prompt
            prompt = self._build_prompt(query, chunks, [])
            
            # Generate response
            response = self.llm_backend.generate(prompt)
            
            # Extract answer and citations
            answer, answer_blocks, citations = self._extract_answer_blocks_and_citations(response, chunks)
            
            return {
                'query': query,
                'num_chunks': len(chunks),
                'prompt_length': len(prompt),
                'response_length': len(response),
                'answer': answer,
                'answer_blocks': [block.model_dump() for block in answer_blocks],
                'citations': [
                    {
                        'file_path': c.file_path,
                        'title': c.title,
                        'snippet': c.snippet
                    }
                    for c in citations
                ],
                'success': True
            }
            
        except Exception as e:
            return {
                'query': query,
                'num_chunks': len(chunks),
                'error': str(e),
                'success': False
            }
