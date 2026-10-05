    #[test]
    #[serial_test::serial]
    fn cline_input_rebuilds_predecessor_cache_for_unchanged_transcript() {
        let home = TempDir::new().unwrap();
        let _env = sandbox_cache_env(home.path());
        let session = home.path().join(".cline/data/sessions/s1");
        fs::create_dir_all(&session).unwrap();
        let path = session.join("s1.messages.json");
        fs::write(&path, r#"{"sessionId":"s1","messages":[{"id":"a1","role":"assistant","ts":1786406085634,"modelInfo":{"id":"deepseek-v4-flash","provider":"opencode-go"},"metrics":{"inputTokens":10,"outputTokens":10,"cacheReadTokens":100,"cacheWriteTokens":50,"cost":0.01}}]}"#).unwrap();
        let fingerprint = SourceFingerprint::check_cline_path_samples_only(&path).unwrap();
        let identity = CacheIdentity::for_client(ClientId::Cline);
        let predecessor = CacheIdentity {
            namespace: identity.namespace,
            parser_version: crate::sessions::roocode::ROO_KILO_TASK_LOG_PARSER_BASE_VERSION + 2,
        };
        let mut legacy = crate::sessions::cline::parse_cline_file(&path);
        assert_eq!(legacy.len(), 1);
        legacy[0].tokens.input = -140;
        let entry = CachedSourceEntry::new(predecessor, &path, fingerprint.clone(), legacy, Vec::new(), None);
        let shard = cache_shard_path(identity, &path);
        ensure_cache_dir(shard.parent().unwrap()).unwrap();
        write_shard_with_limit(&shard, predecessor, &[entry], MAX_CACHE_SHARD_BYTES).unwrap();

        let parsed = crate::parse_all_messages_with_pricing(home.path().to_str().unwrap(), &["cline".to_string()], None);
        assert_eq!(parsed.len(), 1);
        assert_eq!(parsed[0].tokens.input, 0, "unchanged warm sources must not retain negative input");
        assert_eq!(parsed[0].tokens.total(), 160);
        assert_eq!(SourceFingerprint::check_cline_path_samples_only(&path).unwrap(), fingerprint);
        let cache = SourceMessageCache::load();
        let rebuilt = cache.get(identity, &path).unwrap();
        assert_eq!(rebuilt.parser_version, identity.parser_version);
        assert_eq!(rebuilt.messages, parsed);
        let warm = crate::parse_all_messages_with_pricing(home.path().to_str().unwrap(), &["cline".to_string()], None);
        assert_eq!(warm, parsed);
        assert_eq!(cache.get(identity, &path).unwrap().messages, parsed);
    }

