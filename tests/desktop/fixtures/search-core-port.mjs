;(() => {
          const original=window.__TAURI_INTERNALS__.invoke, id=n=>`01900000-0000-7000-8000-${String(n).padStart(12,'0')}`;
          const projectId='11111111-1111-4111-8111-111111111111', hash='a'.repeat(64), traceId='b'.repeat(32);
          const state=window.__SEARCH_TEST__={calls:[],deny:false,loseAck:false,pollFailure:false,running:false,holdAnchor:false,releaseAnchor:null,locked:false};
          const success=body=>({status:200,contentType:'application/json',traceId,etag:null,body:JSON.stringify(body)});
          const denied=()=>({status:409,contentType:'application/problem+json',traceId,etag:null,body:JSON.stringify({
            type:'urn:research-observatory:problem:search-denied',title:'Search needs attention',status:409,
            detail:'Current source rights could not be confirmed.',code:'RO-CORE-SEARCH-DENIED',traceId,retryable:false,remediation:'Review current rights.'})});
          const source={projectId,attachmentId:id(100),documentId:id(101),documentRevisionId:id(102),candidateId:id(103),
            sourceAssertionRevisionId:id(104),versionId:id(105),versionRevisionId:id(106),workId:id(107),workRevisionId:id(108),
            objectSha256:hash,byteLength:100,format:'pdf',provenance:{kind:'local-import'}};
          const execution={projectId,searchRunId:id(2),revisionId:id(3),jobId:id(4),generationId:id(5),sourceWatermark:12,
            inputSha256:hash,resultSha256:hash,resultCount:51,validatedAt:'2026-10-17T00:00:00.000Z',expiresAt:null,
            originalQuery:'title:café',normalizedQuery:'title:"café"',filters:{yearFrom:2020,yearTo:2026},
            rankingVersion:'ro-lexical-best-row-per-leaf-bm25-1',fieldWeights:[8,4,1,2,2,10,1,1],
            scoreMeaning:'weighted-bm25-relevance',semanticState:'unqualified',rerankState:'not-run'};
          const cursor=btoa(JSON.stringify({revisionId:id(3),nextPosition:50})).replace(/=+$/,'');
          const hit=n=>({itemId:id(200+n),workId:source.workId,workRevisionId:source.workRevisionId,position:n,score:1/n,
            title:`Synthetic café record ${n}`,titleTruncated:false,year:2024,
            snippet:{field:'title',start:0,end:11,text:'😀 <script>x',highlights:[{start:2,end:10}],truncated:false},
            source:{revisionId:id(109),source,selection:null,locationState:'unanchored-preview'}});
          const job=commandId=>({projectId,commandId,jobId:id(4),workflowRunId:id(6),state:state.running?'running':'succeeded',
            attemptCount:1,cancellationRequested:false,diagnosticCode:null});
          window.__TAURI_INTERNALS__.invoke=async(command,args)=>{
            if(command==='application_lock_status' && state.locked) return {schemaVersion:'1.0',state:'locked',signInMode:'windows-password',policyRevision:2,
              profileName:null,inactivityTimeoutMinutes:0,configurationState:'valid',reason:'manual',threatDisclosure:'Application-session protection only; this is not Windows-account isolation.',retryAfterSeconds:0,auditSequence:1};
            if(command==='document_reader_anchor_create' && state.holdAnchor){return new Promise(resolve=>{state.releaseAnchor=()=>resolve(null);});}
            const request=args?.request;
            if(command!=='core_api_request'||!request?.path?.startsWith('/projects/search/'))return original(command,args);
            const body=JSON.parse(request.body);state.calls.push({path:request.path,body});
            if(request.path.endsWith('/validate'))return success({valid:true,originalQuery:body.query,normalizedQuery:'title:"café"',
              queryDocument:JSON.stringify({schemaVersion:'1.0',grammarVersion:'ro-search-query-1',analyzerId:'ro-unicode61-diacritics2-1',originalQuery:body.query,normalizedQuery:'title:"café"'}),diagnostic:null});
            if(request.path.endsWith('/run')){
              state.commandId ??= body.commandId;
              if(state.loseAck){state.loseAck=false;throw Error('synthetic lost acknowledgement');}
              return success(job(state.commandId));
            }
            if(state.deny)return denied();
            if(request.path.endsWith('/status')){
              if(state.pollFailure){state.pollFailure=false;return denied();}
              return success(job(state.commandId));
            }
            if(request.path.endsWith('/page')){
              const hits=body.after ? [hit(51)] : Array.from({length:50},(_,n)=>hit(n+1));
              if(state.holdAnchor){const chosen=hits.at(-1);chosen.source.selection={schemaVersion:'1.0',revisionId:id(109),nodeId:id(110),
                normalizedRange:{start:0,end:4}};
                chosen.source.locationState='contained-text-selection';}
              return success({execution,afterCursor:body.after,startPosition:body.after?50:0,hits,nextCursor:body.after?null:cursor});
            }
            if(request.path.endsWith('/explain'))return success({execution,itemId:body.itemId,score:1/51,
              components:[{leafSha256:hash,entryId:hash,field:'title',matchKind:'literal',score:1/51}],
              filterEffect:'membership-only; statistical universe unchanged'});
            if(request.path.endsWith('/cancel'))return success({...job(state.commandId),state:'cancelled',cancellationRequested:true});
            throw Error('Unexpected search request');
          };
        })();