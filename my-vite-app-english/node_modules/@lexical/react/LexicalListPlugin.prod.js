/**
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 *
 */

"use strict";var e=require("@lexical/list"),t=require("@lexical/react/LexicalComposerContext"),r=require("react");exports.ListPlugin=function(){const[i]=t.useLexicalComposerContext();return r.useEffect((()=>{if(!i.hasNodes([e.ListNode,e.ListItemNode]))throw new Error("ListPlugin: ListNode and/or ListItemNode not registered on editor")}),[i]),function(t){r.useEffect((()=>e.registerList(t)),[t])}(i),null};
