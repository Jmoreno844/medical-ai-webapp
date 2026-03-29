/**
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 *
 */

"use strict";var e=require("@lexical/react/LexicalComposerContext"),t=require("react");const r="undefined"!=typeof window&&void 0!==window.document&&void 0!==window.document.createElement?t.useLayoutEffect:t.useEffect;exports.OnChangePlugin=function({ignoreHistoryMergeTagChange:t=!0,ignoreSelectionChange:i=!1,onChange:n}){const[o]=e.useLexicalComposerContext();return r((()=>{if(n)return o.registerUpdateListener((({editorState:e,dirtyElements:r,dirtyLeaves:s,prevEditorState:a,tags:c})=>{i&&0===r.size&&0===s.size||t&&c.has("history-merge")||a.isEmpty()||n(e,o,c)}))}),[o,t,i,n]),null};
