import { FloatButton, Drawer, Input, message as AntMessage } from 'antd'; // Use FloatButton for sticky icon
import { useState, useRef, useEffect } from 'react';
import { CommentOutlined, SendOutlined } from '@ant-design/icons'; // Import icons

const StickyChat = () => {
  const [open, setOpen] = useState(false);
  // Changed messages to store objects for sender differentiation
  const [messages, setMessages] = useState<{ text: string; sender: 'user' | 'bot' }[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false); // Add loading state

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom when messages update
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async () => {
    if (input.trim() === '') {
      AntMessage.warning('Please enter a message.');
      return;
    }

    const userMessage = input;
    setMessages((prevMessages) => [...prevMessages, { text: `You: ${userMessage}`, sender: 'user' }]);
    setInput('');
    setLoading(true); // Start loading

    try {
      // Your backend API call to n8n (which then calls Ollama)
      const res = await fetch('http://localhost:8000/api/chat/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMessage }), // Send 'message' key to match Django backend
      });

      if (!res.ok) {
        throw new Error(`HTTP error! status: ${res.status}`);
      }

      const data = await res.json();
      // Assuming backend sends back a 'response' field
      setMessages((prevMessages) => [...prevMessages, { text: `Bot: ${data.response}`, sender: 'bot' }]);
    } catch (error) {
      console.error('Error sending message:', error);
      AntMessage.error('Failed to get a response from the chatbot.');
      setMessages((prevMessages) => [...prevMessages, { text: 'Bot: Sorry, something went wrong. Please try again.', sender: 'bot' }]);
    } finally {
      setLoading(false); // End loading
    }
  };

  return (
    <>
      {/* Use Ant Design's FloatButton for a more typical sticky icon */}
      <FloatButton
        type="primary"
        icon={<CommentOutlined />} // Chat icon
        style={{ right: 24, bottom: 24, zIndex: 1000 }}
        onClick={() => setOpen(true)}
        tooltip="Open EHS Chatbot"
      />
      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title={<span className="text-xl font-semibold text-gray-800">EHS Chatbot</span>} // Styled title
        placement="right"
        width={window.innerWidth > 768 ? 400 : '90%'} // Responsive width
        bodyStyle={{ padding: '0 16px', display: 'flex', flexDirection: 'column', height: 'calc(100% - 55px)' }}
      >
        <div className="flex-grow overflow-y-auto pr-2"> {/* Added overflow for scrolling */}
          {messages.map((msg, i) => (
            <p
              key={i}
              className={`p-2 rounded-lg my-1 text-sm ${
                msg.sender === 'user'
                  ? 'bg-blue-500 text-white ml-auto rounded-br-none max-w-[80%]'
                  : 'bg-gray-200 text-gray-800 mr-auto rounded-bl-none max-w-[80%]'
              }`}
              style={{ wordBreak: 'break-word' }} // Ensure long words wrap
            >
              {msg.text}
            </p>
          ))}
          <div ref={messagesEndRef} /> {/* Scroll target */}
        </div>
        <Input.Search
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onSearch={sendMessage}
          enterButton={loading ? 'Sending...' : <SendOutlined />} // Show loading on button
          size="large"
          className="mt-4 rounded-md"
          disabled={loading} // Disable input when loading
        />
      </Drawer>
    </>
  );
};

export default StickyChat;