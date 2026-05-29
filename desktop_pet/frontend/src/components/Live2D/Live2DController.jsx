import { forwardRef, useImperativeHandle, useRef } from 'react';
import Live2DDisplay from './Live2DModel';

const Live2DController = forwardRef(({ modelId }, ref) => {
  const live2dRef = useRef(null);

  useImperativeHandle(ref, () => ({
    showExpression: (expression, active = true) => {
      if (live2dRef.current) {
        live2dRef.current.showExpression(expression, active);
      }
    },

    setTracking: (enabled) => {
      if (live2dRef.current) {
        live2dRef.current.setTracking(enabled);
      }
    },

    resetExpression: () => {
      if (live2dRef.current) {
        setTimeout(() => {
          live2dRef.current.showExpression('', false);
        }, 1000);
      }
    },

    switchModel: (newModelId) => {
      if (live2dRef.current) {
        return live2dRef.current.switchModel(newModelId);
      }
    },

    getLive2DRef: () => live2dRef
  }));

  return <Live2DDisplay ref={live2dRef} modelId={modelId} />;
});

Live2DController.displayName = 'Live2DController';

export default Live2DController;