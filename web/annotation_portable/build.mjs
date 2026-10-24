import {build} from 'vite';
import react from '@vitejs/plugin-react';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
const root=fileURLToPath(new URL('.',import.meta.url));
await build({root,configFile:false,plugins:[react()],base:'./',build:{outDir:resolve(root,'dist/client'),emptyOutDir:true}});
await build({root,configFile:false,publicDir:false,build:{ssr:resolve(root,'server.ts'),outDir:resolve(root,'dist/server'),emptyOutDir:true,rollupOptions:{output:{entryFileNames:'server.mjs'}}},ssr:{noExternal:['drizzle-orm']}});
