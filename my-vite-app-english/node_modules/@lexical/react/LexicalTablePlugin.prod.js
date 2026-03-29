/**
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 *
 */

"use strict";var e=require("@lexical/react/LexicalComposerContext"),r=require("@lexical/table"),l=require("react");exports.TablePlugin=function({hasCellMerge:t=!0,hasCellBackgroundColor:a=!0,hasTabHandler:o=!0,hasHorizontalScroll:s=!1}){const[n]=e.useLexicalComposerContext();return l.useEffect((()=>{r.setScrollableTablesActive(n,s)}),[n,s]),l.useEffect((()=>r.registerTablePlugin(n)),[n]),l.useEffect((()=>r.registerTableSelectionObserver(n,o)),[n,o]),l.useEffect((()=>{if(!t)return r.registerTableCellUnmergeTransform(n)}),[n,t]),l.useEffect((()=>{if(!a)return n.registerNodeTransform(r.TableCellNode,(e=>{null!==e.getBackgroundColor()&&e.setBackgroundColor(null)}))}),[n,a,t]),null};
