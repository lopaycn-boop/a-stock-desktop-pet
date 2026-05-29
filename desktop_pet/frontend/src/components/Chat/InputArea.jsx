import React, { useState } from 'react';
import VoiceInput from './VoiceInput';

const InputArea = ({ 
    onSendMessage,
    fileInputRef,
    onFileUpload, 
    disabled,
    isAiSpeaking,
    onRecordStart 
  }) => {
    
    // ✅ 新增：让组件自己管理输入框的内容
    const [localInput, setLocalInput] = useState(""); 

    // 发送文本消息逻辑
    const handleSendMessage = () => {
      if (localInput.trim() && !disabled) {
        onSendMessage(localInput); // 把最终结果传给父组件
        setLocalInput('');         // 清空输入框
      }
    };
  
    const handleKeyPress = (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSendMessage();
      }
    };

    // 处理录音完成
    const handleAudioCaptured = (audioBlob) => {
        const audioFile = new File([audioBlob], "voice_command.wav", { type: "audio/wav" });
        onFileUpload(audioFile, true); 
    };
  
    return (
      <div className="chat-input-container">
        {/* 上传按钮 */}
        <button
          className="icon-button"
          style={{ marginRight: 8 }}
          onClick={() => fileInputRef.current?.click()}
          title="上传文档"
          disabled={disabled}
        >
          📁
        </button>

        <input
          type="file"
          ref={fileInputRef}
          style={{ display: 'none' }}
          accept=".pdf,.doc,.docx"
          onChange={e => e.target.files[0] && onFileUpload(e.target.files[0])}
        />

        {/* 语音按钮区域 */}
        <div style={{ marginRight: 8 }}>
            <VoiceInput 
                onAudioCaptured={handleAudioCaptured} 
                onRecordStart={onRecordStart}
                disabled={disabled}
                isAiSpeaking={isAiSpeaking} 
            />
        </div>

        {/* 聊天输入框 */}
        <input
          className="chat-input"
          value={localInput}                  // 👈 绑定本地变量
          onChange={(e) => setLocalInput(e.target.value)} // 👈 更新本地变量
          onKeyDown={handleKeyPress}
          placeholder="跟小土豆聊聊..."
          disabled={disabled}
        />
        
        <button 
          className="chat-submit-button"
          onClick={handleSendMessage}
          disabled={disabled || !localInput.trim()}
        >
          发送
        </button>
      </div>
    );
  };
  
  export default InputArea;