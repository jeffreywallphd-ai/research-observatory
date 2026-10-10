import {resolve,join,isAbsolute} from "node:path";
import {build,loadConfigFromFile} from "../../../node_modules/vite/dist/node/index.js";
const repo=resolve(import.meta.dirname,"../../.."),output=process.argv[2];
if (!output || !isAbsolute(output) || !resolve(output).startsWith(join(repo,"artifacts","tmp")+(process.platform === "win32" ? "\\" : "/"))) throw new Error("Use owned artifacts/tmp output");
const {config}=await loadConfigFromFile({command:"build",mode:"production"},join(repo,"apps/desktop/vite.product.config.ts"));
const actual=join(repo,"tests/desktop/fixtures/reprocessing-navigation-doubles.tsx");
const doubles=join(repo,"tests/desktop/fixtures/quality-navigation-doubles.tsx");
await build({...config,configFile:false,root:join(repo,"apps/desktop"),logLevel:"silent",
  plugins:[{name:"task-owned-reprocessing-navigation",enforce:"pre",resolveId(source,importer){
    if (importer?.replaceAll("\\","/").endsWith("/src/app/ApplicationRuntime.tsx")) {
      if (source === "./ParsingQualityWorkspace") return actual;
      if (["./ProjectsWorkspace","@research-observatory/contracts/core-api"].includes(source)) return doubles;
    }
  }},...config.plugins],
  build:{...config.build,outDir:output,emptyOutDir:false,minify:false,rollupOptions:{input:join(repo,"tests/desktop/fixtures/quality-navigation.tsx"),output:{entryFileNames:"reprocessing-navigation.js",chunkFileNames:"[name].js",assetFileNames:"[name][extname]"}}}});
