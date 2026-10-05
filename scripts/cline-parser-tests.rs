
#[cfg(test)]
mod cline_input_tests {
    use super::*;
    use crate::aggregator::{aggregate_by_date, aggregate_by_session, DailyFold};
    use tempfile::TempDir;

    fn fixture(input: i64, output: i64, read: i64, write: i64) -> Value {
        serde_json::json!({
            "id": "a1", "role": "assistant", "ts": 1786406085634_i64,
            "modelInfo": {"id": "deepseek-v4-flash", "provider": "opencode-go"},
            "metrics": {"inputTokens": input, "outputTokens": output,
                "cacheReadTokens": read, "cacheWriteTokens": write, "cost": 0.01}
        })
    }

    fn parse(entries: Vec<Value>) -> Vec<UnifiedMessage> {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("s1.messages.json");
        std::fs::write(
            &path,
            serde_json::to_vec(&serde_json::json!({
                "sessionId": "s1", "messages": entries
            }))
            .unwrap(),
        )
        .unwrap();
        parse_cline_file(&path)
    }

    #[test]
    fn cline_input_cannot_be_negative_when_cache_exceeds_gross_input() {
        for (input, output, read, write) in [
            (10, 10, 100, 50),
            (10, 10, 11, 0),
            (10, 10, 0, 11),
            (10, 10, 6, 5),
            (0, 1, i64::MAX, i64::MAX),
        ] {
            let messages = parse(vec![fixture(input, output, read, write)]);
            assert_eq!(messages.len(), 1);
            let message = &messages[0];
            assert_eq!(message.tokens.input, 0, "read={read}, write={write}");
            assert_eq!(message.tokens.output, output);
            assert_eq!(message.tokens.cache_read, read);
            assert_eq!(message.tokens.cache_write, write);
            assert_eq!(
                message.tokens.total(),
                output.saturating_add(read).saturating_add(write)
            );
            assert_eq!(message.cost, 0.01);
            assert!(message.has_authoritative_cost());
        }
    }

    #[test]
    fn cline_input_keeps_cache_only_messages_without_reported_cost() {
        let mut entry = fixture(0, 0, 100, 50);
        entry["metrics"].as_object_mut().unwrap().remove("cost");
        let messages = parse(vec![entry]);
        assert_eq!(
            messages.len(),
            1,
            "cache usage must survive the empty-message filter"
        );
        assert_eq!(messages[0].tokens.input, 0);
        assert_eq!(messages[0].tokens.total(), 150);
        assert!(!messages[0].has_authoritative_cost());
    }

    #[test]
    fn cline_input_daily_session_and_streamed_totals_agree() {
        let bad = fixture(10, 10, 100, 50);
        let mut normal = fixture(250, 30, 40, 10);
        normal["id"] = serde_json::json!("a2");
        normal["modelInfo"]["id"] = serde_json::json!("other-model");
        let messages = parse(vec![bad, normal]);
        let mut fold = DailyFold::default();
        for message in &messages {
            fold.add(message);
        }
        let streamed = fold.finish();
        let daily = aggregate_by_date(messages.clone());
        let sessions = aggregate_by_session(messages);
        assert_eq!(daily.len(), 1);
        assert_eq!(sessions.len(), 1);
        assert_eq!(daily[0].totals.tokens, 440);
        assert_eq!(daily[0].token_breakdown.total(), 440);
        assert_eq!(
            daily[0]
                .clients
                .iter()
                .map(|c| c.tokens.total())
                .sum::<i64>(),
            440
        );
        assert_eq!(streamed[0].totals, daily[0].totals);
        assert_eq!(streamed[0].token_breakdown, daily[0].token_breakdown);
        let mut streamed_clients = streamed[0].clients.clone();
        let mut daily_clients = daily[0].clients.clone();
        streamed_clients.sort_by(|a, b| a.model_id.cmp(&b.model_id));
        daily_clients.sort_by(|a, b| a.model_id.cmp(&b.model_id));
        assert_eq!(streamed_clients, daily_clients);
        assert_eq!(sessions[0].totals.tokens, 440);
        assert_eq!(sessions[0].token_breakdown.total(), 440);
        assert_eq!(
            sessions[0]
                .clients
                .iter()
                .map(|c| c.tokens.total())
                .sum::<i64>(),
            440
        );
        assert_eq!(daily[0].totals.messages, 2);
        assert_eq!(daily[0].totals.cost, 0.02);
    }

    #[test]
    fn cline_input_preserves_valid_cache_inclusive_metrics() {
        let messages = parse(vec![fixture(1000, 25, 200, 50)]);
        assert_eq!(messages.len(), 1);
        assert_eq!(messages[0].tokens.input, 750);
        assert_eq!(messages[0].tokens.total(), 1025);
    }
}
