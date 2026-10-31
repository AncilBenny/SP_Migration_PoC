"""MSAL auth + Graph staging regression tests. No browser or tenant network."""
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from poc.entra_auth import DelegatedAuthConfig, EntraAuthError, EntraDelegatedTokenProvider, DELEGATED_READ_SCOPES
from poc.graph_transport import GraphBinaryFetcher, HttpResult
from poc.graph_assets import stage_graph_files

TENANT='11111111-1111-4111-8111-111111111111'
CLIENT='22222222-2222-4222-8222-222222222222'

class FakeMSAL:
    instances=[]
    results=[]
    silent=None
    accounts=[]
    failure=None
    class SerializableTokenCache:
        pass
    class PublicClientApplication:
        def __init__(self, client_id, *, authority, token_cache):
            FakeMSAL.instances.append(self)
            self.client_id=client_id
            self.authority=authority
            self.token_cache=token_cache
            self.calls=[]
        def get_accounts(self, username=None):
            self.calls.append(('accounts',username))
            if FakeMSAL.failure=='accounts':
                raise ValueError('Bearer secret/private?token=123')
            return FakeMSAL.accounts
        def acquire_token_silent_with_error(self, scopes, *, account):
            self.calls.append(('silent',scopes,account))
            if FakeMSAL.failure=='silent':
                raise RuntimeError('token leaked from provider exception')
            return FakeMSAL.silent
        def acquire_token_interactive(self, *, scopes, login_hint=None):
            self.calls.append(('interactive',scopes,login_hint))
            if FakeMSAL.failure=='interactive':
                raise RuntimeError('password/token info from provider')
            return FakeMSAL.results.pop(0)

class EntraAuthTests(unittest.TestCase):
    def setUp(self):
        FakeMSAL.instances.clear()
        FakeMSAL.results=[{'access_token':'TOKEN_SECRET','scope':'Files.Read User.Read'}]
        FakeMSAL.silent=None
        FakeMSAL.accounts=[]
        FakeMSAL.failure=None
        self.cfg=DelegatedAuthConfig(TENANT,CLIENT)

    def test_authority_and_no_secrets_in_readiness(self):
        self.assertEqual(self.cfg.authority,'https://login.microsoftonline.com/'+TENANT)
        report=self.cfg.readiness()
        self.assertFalse(report['permissionApproved'])
        self.assertEqual(report['graphAuthorization'],'not-verified')
        self.assertEqual(report['tokenCache'],'process-memory-only')
        self.assertNotIn('TOKEN_SECRET',json.dumps(report))

    def test_untrusted_authority_and_ids_rejected(self):
        for value in ('common','organizations','https://evil.example/t',TENANT+'/x','00000000-0000-0000-0000-000000000000','x'*36):
            with self.subTest(value=value),self.assertRaises(EntraAuthError):
                DelegatedAuthConfig(value,CLIENT)
        with self.assertRaises(EntraAuthError):
            DelegatedAuthConfig(TENANT,'abc')

    def test_reject_wide_write_and_dot_default_scopes(self):
        self.assertEqual(len(DELEGATED_READ_SCOPES),3)
        for scope in ('Files.Read.All','Files.ReadWrite','Sites.Read.All','Sites.FullControl.All',
                      'https://graph.microsoft.com/.default','User.Read','files.read','Files.Read Sites.Read.All'):
            with self.subTest(scope=scope),self.assertRaisesRegex(EntraAuthError,'ENTRA_SCOPE_NOT_ALLOWED'):
                DelegatedAuthConfig(TENANT,CLIENT,scope)
        for scope in DELEGATED_READ_SCOPES:
            self.assertEqual(DelegatedAuthConfig(TENANT,CLIENT,scope).scope,scope)

    def test_interactive_pkce_library_flow(self):
        provider=EntraDelegatedTokenProvider(self.cfg,msal_module=FakeMSAL)
        self.assertEqual(provider(),'TOKEN_SECRET')
        app=FakeMSAL.instances[0]
        self.assertEqual(app.authority,self.cfg.authority)
        self.assertIsInstance(app.token_cache,FakeMSAL.SerializableTokenCache)
        self.assertEqual(app.calls,[('accounts',None),('interactive',['Files.Read'],None)])

    def test_silent_token_refresh_before_interactive(self):
        FakeMSAL.accounts=[{'home_account_id':'one'}]
        FakeMSAL.silent={'access_token':'SILENT_SECRET','scope':'Files.Read'}
        provider=EntraDelegatedTokenProvider(self.cfg,msal_module=FakeMSAL)
        self.assertEqual(provider(),'SILENT_SECRET')
        self.assertEqual([c[0] for c in FakeMSAL.instances[0].calls],['accounts','silent'])

    def test_silent_only_never_launches_browser(self):
        cfg=DelegatedAuthConfig(TENANT,CLIENT,allow_interactive=False)
        provider=EntraDelegatedTokenProvider(cfg,msal_module=FakeMSAL)
        with self.assertRaisesRegex(EntraAuthError,'ENTRA_INTERACTIVE_REQUIRED'):
            provider()
        self.assertNotIn('interactive',[c[0] for c in FakeMSAL.instances[0].calls])
        FakeMSAL.accounts=[{'home_account_id':'one'}]
        FakeMSAL.silent={'error':'interaction_required','error_description':'Bearer SUPERSECRET'}
        with self.assertRaisesRegex(EntraAuthError,'ENTRA_REAUTH_REQUIRED') as err:
            provider()
        self.assertNotIn('SUPERSECRET',str(err.exception))

    def test_multiple_accounts_fail_closed(self):
        FakeMSAL.accounts=[{'home_account_id':'a'},{'home_account_id':'b'}]
        provider=EntraDelegatedTokenProvider(self.cfg,msal_module=FakeMSAL)
        with self.assertRaisesRegex(EntraAuthError,'ENTRA_MULTIPLE_ACCOUNTS'):
            provider()
        self.assertEqual([c[0] for c in FakeMSAL.instances[0].calls],['accounts'])

    def test_login_hint_selects_account(self):
        cfg=DelegatedAuthConfig(TENANT,CLIENT,login_hint='operator@example.org')
        provider=EntraDelegatedTokenProvider(cfg,msal_module=FakeMSAL)
        self.assertEqual(provider(),'TOKEN_SECRET')
        app=FakeMSAL.instances[0]
        self.assertEqual(app.calls[0],('accounts','operator@example.org'))
        self.assertEqual(app.calls[-1],('interactive',['Files.Read'],'operator@example.org'))

    def test_msal_errors_redacted(self):
        for target in ('accounts','interactive'):
            FakeMSAL.failure=target
            provider=EntraDelegatedTokenProvider(self.cfg,msal_module=FakeMSAL)
            with self.assertRaises(EntraAuthError) as err:
                provider()
            self.assertNotIn('secret',str(err.exception).lower())
            self.assertNotIn('token=',str(err.exception).lower())
        FakeMSAL.failure='silent'
        FakeMSAL.accounts=[{'home_account_id':'one'}]
        provider=EntraDelegatedTokenProvider(self.cfg,msal_module=FakeMSAL)
        with self.assertRaisesRegex(EntraAuthError,'ENTRA_SILENT_ACQUISITION_FAILED'):
            provider()

    def test_errors_and_scope_downgrade(self):
        for result in ({'error':'access_denied','error_description':'SECRET'},
                       {'access_token':'x y','scope':'Files.Read'},
                       {'access_token':'SAFE','scope':'User.Read'},
                       {'access_token':'SAFE','scope':42},
                       {'access_token':123,'scope':'Files.Read'}):
            FakeMSAL.results=[result]
            provider=EntraDelegatedTokenProvider(self.cfg,msal_module=FakeMSAL)
            with self.assertRaises(EntraAuthError) as err:
                provider()
            self.assertNotIn('SECRET',str(err.exception))

    def test_msal_missing_redacted(self):
        with patch.dict('sys.modules',{'msal':None}):
            with self.assertRaisesRegex(EntraAuthError,'ENTRA_MSAL_NOT_INSTALLED'):
                EntraDelegatedTokenProvider(self.cfg)

    def test_provider_graph_redirect_does_not_leak_bearer(self):
        provider=EntraDelegatedTokenProvider(self.cfg,msal_module=FakeMSAL)
        calls=[]
        def request(url,headers,max_bytes,timeout):
            calls.append((url,dict(headers)))
            if len(calls)==1:
                return HttpResult(302,{'location':'https://tenant.files.1drv.com/download?sig=private'},b'')
            return HttpResult(200,{'content-type':'application/pdf'},b'%PDF-1.6')
        fetcher=GraphBinaryFetcher(provider,redirect_hosts={'tenant.files.1drv.com'},executor=request)
        self.assertEqual(fetcher('drive','item')[0],b'%PDF-1.6')
        self.assertEqual(calls[0][1],{'Authorization':'Bearer TOKEN_SECRET'})
        self.assertEqual(calls[1][1],{})

    def test_staging_preserves_redacted_entra_failure(self):
        with TemporaryDirectory() as d:
            plan={'items':[{'status':'graph-identity-resolved','nodeId':'n1','kind':'image',
                'graphItem':{'driveId':'d1','itemId':'i1','name':'a.png','mimeType':'image/png'}}]}
            def fail(*args):
                raise EntraAuthError('ENTRA_INTERACTIVE_REQUIRED')
            report=stage_graph_files(plan,Path(d),fetcher=fail)
            row=report['items'][0]
            self.assertEqual(row['stageStatus'],'stage-failed')
            self.assertEqual(row['errorCode'],'ENTRA_INTERACTIVE_REQUIRED')

class EntraCLITests(unittest.TestCase):
    def test_readiness_command_hides_credentials(self):
        from poc.__main__ import main
        with patch.dict(os.environ,{'MIGRATION_ENTRA_TENANT_ID':TENANT,
             'MIGRATION_ENTRA_CLIENT_ID':CLIENT,'MIGRATION_GRAPH_ACCESS_TOKEN':'PRIVATE_TOKEN'}):
            with patch('sys.argv',['poc','graph-auth-check']),redirect_stdout(io.StringIO()) as output:
                main()
        data=json.loads(output.getvalue())
        self.assertEqual(data['scopeRequested'],'Files.Read')
        self.assertFalse(data['permissionApproved'])
        self.assertNotIn(TENANT,output.getvalue())
        self.assertNotIn(CLIENT,output.getvalue())
        self.assertNotIn('PRIVATE_TOKEN',output.getvalue())

    def test_entra_mode_empty_plan_no_login(self):
        from poc.__main__ import main
        with TemporaryDirectory() as d:
            plan=Path(d)/'plan.json'
            plan.write_text(json.dumps({'items':[]}),encoding='utf-8')
            with patch.dict(os.environ,{'MIGRATION_ENTRA_TENANT_ID':TENANT,
                 'MIGRATION_ENTRA_CLIENT_ID':CLIENT}),patch.dict('sys.modules',{'msal':FakeMSAL}),\
                 patch('sys.argv',['poc','graph-stage','--plan',str(plan),'--out',str(Path(d)/'staged'),
                                   '--allow-download-host','tenant.files.1drv.com','--auth-mode','entra-delegated',
                                   '--silent-only']),redirect_stdout(io.StringIO()) as output:
                main()
            self.assertEqual(json.loads(output.getvalue())['items'],[])
            self.assertTrue((Path(d)/'staged'/'graph-staging-report.json').exists())

    def test_bad_authority_rejected_before_msal(self):
        from poc.__main__ import main
        with patch.dict(os.environ,{'MIGRATION_ENTRA_TENANT_ID':'common',
              'MIGRATION_ENTRA_CLIENT_ID':CLIENT}),patch('sys.argv',['poc','graph-auth-check']),\
              redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(SystemExit,'ENTRA_INVALID_IDENTIFIER'):
                main()
