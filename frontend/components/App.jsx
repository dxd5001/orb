function App() {
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState("");
  const [searchMode, setSearchMode] = useState("auto");
  const [isLoading, setIsLoading] = useState(false);
  const [status, setStatus] = useState({ index_status: "not_indexed" });
  const [config, setConfig] = useState({});
  const [showConfig, setShowConfig] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    loadStatus();
    loadConfig();
  }, []);

  const createObsidianUri = (filePath) => {
    // Convert file path to Obsidian URI format
    // Example: /path/to/vault/2026-04-01.md -> obsidian://open?file=2026-04-01
    if (!filePath || typeof filePath !== 'string') return "#";

    try {
      // Extract filename from path
      const filename = filePath.split("/").pop().replace(".md", "");
      return `obsidian://open?file=${encodeURIComponent(filename)}`;
    } catch (error) {
      console.error('Error creating Obsidian URI:', error);
      return "#";
    }
  };

  const renderAnswerBlocks = (answerBlocks) => {
    try {
      if (!answerBlocks || answerBlocks.length === 0) {
        return null;
      }

      return (
        <div className="answer-blocks">
          {answerBlocks.map((block, index) => {
            if (!block || typeof block !== 'object') {
              console.warn('Invalid block at index', index, ':', block);
              return null;
            }

            return (
              <div
                key={index}
                className={`answer-block answer-block-${block.type || "summary"}`}
              >
                {block.title && (
                  <div className="answer-block-title">{block.title}</div>
                )}
                {block.content && (
                  <div className="answer-block-content">{block.content}</div>
                )}
                {block.items && Array.isArray(block.items) && block.items.length > 0 && (
                  <ul className="answer-block-items">
                    {block.items.map((item, itemIndex) => (
                      <li key={itemIndex}>{item}</li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      );
    } catch (error) {
      console.error('Error in renderAnswerBlocks:', error);
      return (
        <div className="error-message">
          Error rendering answer blocks. Please check the console for details.
        </div>
      );
    }
  };

  const loadStatus = async () => {
    try {
      const response = await http.get("/api/status");
      setStatus(response);
    } catch (error) {
      console.error("Failed to load status:", error);
    }
  };

  const loadConfig = async () => {
    try {
      const response = await http.get("/api/config");
      setConfig(response.config);
    } catch (error) {
      console.error("Failed to load config:", error);
    }
  };

  const handleSendMessage = async () => {
    if (!inputValue.trim() || isLoading) return;

    const messageToSend = inputValue.trim();
    const userMessage = { role: "user", content: messageToSend };
    setMessages((prev) => [...prev, userMessage]);
    setInputValue("");
    setIsLoading(true);

    try {
      console.log("Sending message:", messageToSend);
      const response = await http.post("/api/chat", {
        query: messageToSend,
        search_mode: searchMode,
        history: messages.slice(-20), // Send last 20 messages (10 turns) as history
      });
      console.log("Received response:", response);

      const assistantMessage = {
        role: "assistant",
        content: response.answer,
        answerBlocks: response.answer_blocks || [],
        citations: response.citations || [],
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error("Error sending message:", error);
      const errorMessage = {
        role: "assistant",
        content: "Sorry, I encountered an error while processing your request.",
        isError: true,
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleIndexVault = async () => {
    setIsLoading(true);
    try {
      await http.post("/api/index");
      await loadStatus();
      const successMessage = {
        role: "assistant",
        content: "Vault indexing started successfully!",
        isSuccess: true,
      };
      setMessages((prev) => [...prev, successMessage]);
    } catch (error) {
      console.error("Error indexing vault:", error);
      const errorMessage = {
        role: "assistant",
        content: "Failed to start vault indexing.",
        isError: true,
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleConfigUpdate = async (newConfig) => {
    try {
      await http.put("/api/config", newConfig);
      await loadConfig();
      await loadStatus();
      // Show success message
      const successMessage = {
        role: "assistant",
        content: "Configuration updated successfully!",
        isSuccess: true,
      };
      setMessages((prev) => [...prev, successMessage]);
    } catch (error) {
      console.error("Error updating config:", error);
      const errorMessage = {
        role: "assistant",
        content: "Failed to update configuration.",
        isError: true,
      };
      setMessages((prev) => [...prev, errorMessage]);
    }
  };

  const getStatusIndicator = () => {
    let statusClass = "status-not-indexed";
    if (status.index_status === "ready") statusClass = "status-ready";
    else if (status.index_status === "indexing")
      statusClass = "status-indexing";

    return <span className={`status-indicator ${statusClass}`}></span>;
  };

  const handleKeyPress = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className="app">
      <div className="sidebar">
        <h2>Obsidian RAG Chatbot</h2>

        <div className="config-section">
          <div className="config-title">{getStatusIndicator()} Status</div>
          <p style={{ fontSize: "0.9em", color: "#bdc3c7" }}>
            {status.index_status === "ready"
              ? "Ready to chat"
              : status.index_status === "not_indexed"
                ? "Not indexed"
                : "Indexing..."}
          </p>
          {status.total_chunks > 0 && (
            <p style={{ fontSize: "0.8em", color: "#bdc3c7" }}>
              {status.total_chunks} chunks indexed
            </p>
          )}

          {status.index_status !== "ready" && (
            <button
              className="config-button"
              onClick={handleIndexVault}
              disabled={isLoading || status.index_status === "indexing"}
            >
              {status.index_status === "indexing"
                ? "Indexing..."
                : "Index Vault"}
            </button>
          )}
        </div>

        <div className="config-section">
          <div className="config-title">Search Mode</div>
          <div className="search-mode-group">
            <label className="search-mode-label">Mode:</label>
            <select
              className="search-mode-select"
              value={searchMode}
              onChange={(e) => setSearchMode(e.target.value)}
            >
              <option value="auto">Auto</option>
              <option value="semantic">Semantic</option>
              <option value="keyword">Keyword</option>
              <option value="hybrid">Hybrid</option>
            </select>
          </div>
        </div>

        <div className="config-section">
          <button
            className="config-button"
            onClick={() => setShowConfig(!showConfig)}
          >
            {showConfig ? "Hide" : "Show"} Configuration
          </button>
        </div>

        {showConfig && (
          <div className="config-section">
            <div className="config-title">Configuration</div>
            <div className="config-form">
              <div className="config-field">
                <label>LLM Base URL:</label>
                <input
                  type="text"
                  value={config.llm_base_url || ""}
                  onChange={(e) =>
                    setConfig({ ...config, llm_base_url: e.target.value })
                  }
                  placeholder="http://localhost:8000"
                />
              </div>
              <div className="config-field">
                <label>LLM Model:</label>
                <input
                  type="text"
                  value={config.llm_model || ""}
                  onChange={(e) =>
                    setConfig({ ...config, llm_model: e.target.value })
                  }
                  placeholder="qwen/qwen2.5-7b-instruct"
                />
              </div>
              <div className="config-field">
                <label>Embedding Model:</label>
                <input
                  type="text"
                  value={config.embedding_model || ""}
                  onChange={(e) =>
                    setConfig({ ...config, embedding_model: e.target.value })
                  }
                  placeholder="sentence-transformers/all-MiniLM-L6-v2"
                />
              </div>
              <div className="config-field">
                <label>Vault Path:</label>
                <input
                  type="text"
                  value={config.vault_path || ""}
                  onChange={(e) =>
                    setConfig({ ...config, vault_path: e.target.value })
                  }
                  placeholder="/path/to/your/obsidian/vault"
                />
              </div>
              <div className="config-field">
                <label>Chunk Size:</label>
                <input
                  type="number"
                  value={config.chunk_size || 1000}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      chunk_size: parseInt(e.target.value),
                    })
                  }
                  min="100"
                  max="4000"
                />
              </div>
              <div className="config-field">
                <label>Chunk Overlap:</label>
                <input
                  type="number"
                  value={config.chunk_overlap || 200}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      chunk_overlap: parseInt(e.target.value),
                    })
                  }
                  min="0"
                  max="1000"
                />
              </div>
              <button
                className="config-button"
                onClick={() => handleConfigUpdate(config)}
                disabled={isLoading}
              >
                Save Configuration
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="main-content">
        <div className="header">
          <h1>Obsidian RAG Chatbot</h1>
        </div>

        <div className="chat-container">
          <div className="messages">
            {messages.length === 0 && (
              <div
                style={{
                  textAlign: "center",
                  color: "#666",
                  marginTop: "50px",
                }}
              >
                <h3>Welcome to Obsidian RAG Chatbot!</h3>
                <p>Start by asking a question about your vault content.</p>
                {status.index_status === "not_indexed" && (
                  <p style={{ color: "#e74c3c" }}>
                    Please index your vault first using the "Index Vault"
                    button.
                  </p>
                )}
              </div>
            )}

            {messages.map((message, index) => {
              try {
                if (!message || typeof message !== 'object') {
                  console.warn('Invalid message at index', index, ':', message);
                  return null;
                }

                return (
                  <div key={index} className={`message ${message.role || 'unknown'}-message`}>
                    {message.content && (
                      <div className="message-content">{message.content}</div>
                    )}

                    {message.answerBlocks && Array.isArray(message.answerBlocks) &&
                      renderAnswerBlocks(message.answerBlocks)}

                    {message.citations && Array.isArray(message.citations) && message.citations.length > 0 && (
                      <div className="citations">
                        <h4>Sources:</h4>
                        {message.citations.map((citation, i) => {
                          if (!citation || typeof citation !== 'object') {
                            console.warn('Invalid citation at index', i, ':', citation);
                            return null;
                          }
                          
                          return (
                            <div key={i} className="citation">
                              <div className="citation-title">
                                <a
                                  href={createObsidianUri(citation.source_path)}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="citation-link"
                                  title="Open in Obsidian"
                                >
                                  {citation.source_path ? citation.source_path.split('/').pop().replace('.md', '') : 'Unknown'}
                                </a>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {message.isError && (
                      <div style={{ marginTop: "10px", fontSize: "0.9em" }}>
                        <span className="error-message">{message.content}</span>
                      </div>
                    )}

                    {message.isSuccess && (
                      <div style={{ marginTop: "10px", fontSize: "0.9em" }}>
                        <span className="success-message">{message.content}</span>
                      </div>
                    )}
                  </div>
                );
              } catch (error) {
                console.error('Error rendering message at index', index, ':', error);
                return (
                  <div key={index} className="message error-message">
                    Error rendering message. Please check the console for details.
                  </div>
                );
              }
            })}

            <div ref={messagesEndRef} />
          </div>

          <div className="input-container">
            {status.index_status !== "ready" && (
              <div style={{ fontSize: "0.9em", color: "#666" }}>
                {status.index_status === "not_indexed"
                  ? "Please index your vault first to start chatting."
                  : "Indexing in progress..."}
              </div>
            )}
            <input
              type="text"
              className="input-field"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder={
                status.index_status === "ready"
                  ? "Ask a question about your vault..."
                  : "Please index vault first..."
              }
              disabled={isLoading || status.index_status !== "ready"}
            />
            <button
              className="send-button"
              onClick={handleSendMessage}
              disabled={
                isLoading ||
                !inputValue.trim() ||
                status.index_status !== "ready"
              }
            >
              {isLoading ? <span className="loading">⟳</span> : "Send"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
