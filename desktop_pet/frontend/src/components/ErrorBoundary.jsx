import React from 'react';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo });
    console.error('[ErrorBoundary]', error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 999999,
          background: 'linear-gradient(135deg, #0f0c29 0%, #1a1a2e 50%, #16213e 100%)',
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          color: '#fff', fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif',
        }}>
          <div style={{ fontSize: 64, marginBottom: 16 }}>🥔</div>
          <h2 style={{ margin: 0, fontSize: 20, color: '#ff8a80' }}>
            {this.props.fallbackTitle || '小土豆遇到了一点问题'}
          </h2>
          <p style={{ margin: '8px 0 24px', fontSize: 14, color: 'rgba(255,255,255,0.5)', maxWidth: 320, textAlign: 'center' }}>
            {this.props.fallbackMessage || '别担心，数据已保存。点击重置或刷新页面即可恢复。'}
          </p>
          <div style={{ display: 'flex', gap: 12 }}>
            <button onClick={this.handleReset} style={{
              padding: '10px 24px', borderRadius: 12, border: 'none',
              background: '#69f0ae', color: '#1a1a2e', fontSize: 14, fontWeight: 600, cursor: 'pointer',
            }}>
              🔄 重置界面
            </button>
            <button onClick={this.handleReload} style={{
              padding: '10px 24px', borderRadius: 12,
              border: '1px solid rgba(255,255,255,0.2)', background: 'transparent',
              color: '#ccc', fontSize: 14, cursor: 'pointer',
            }}>
              🔃 刷新页面
            </button>
          </div>
          {this.state.error && (
            <details style={{ marginTop: 24, maxWidth: 400, width: '100%' }}>
              <summary style={{ fontSize: 12, color: 'rgba(255,255,255,0.3)', cursor: 'pointer' }}>
                错误详情
              </summary>
              <pre style={{
                fontSize: 11, color: '#ff8a80', background: 'rgba(255,255,255,0.05)',
                padding: 12, borderRadius: 8, overflow: 'auto', maxHeight: 200,
                whiteSpace: 'pre-wrap', wordBreak: 'break-all',
              }}>
                {this.state.error.toString()}
                {this.state.errorInfo?.componentStack}
              </pre>
            </details>
          )}
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;