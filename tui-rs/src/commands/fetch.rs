use serde::Deserialize;
use tokio::process::Command;
use tokio::sync::mpsc;

use crate::app::AppEvent;
use crate::db::models::ScoredPaper;

#[derive(Deserialize)]
struct DailyResult {
    author_papers: Vec<ScoredPaper>,
    scored_papers: Vec<ScoredPaper>,
}

pub fn fetch_daily(tx: mpsc::UnboundedSender<AppEvent>, days: u32, limit: u32) {
    tokio::spawn(async move {
        let output = Command::new("uv")
            .args([
                "run",
                "axp",
                "daily",
                "--days",
                &days.to_string(),
                "--limit",
                &limit.to_string(),
                "--json",
            ])
            .output()
            .await;

        match output {
            Ok(out) if out.status.success() => {
                let stdout = String::from_utf8_lossy(&out.stdout);
                match serde_json::from_str::<DailyResult>(&stdout) {
                    Ok(result) => {
                        let _ = tx.send(AppEvent::DailyFetched {
                            author_papers: result.author_papers,
                            scored_papers: result.scored_papers,
                        });
                    }
                    Err(e) => {
                        let _ = tx.send(AppEvent::Toast {
                            message: format!("Parse error: {e}"),
                            is_error: true,
                        });
                    }
                }
            }
            Ok(out) => {
                let stderr = String::from_utf8_lossy(&out.stderr);
                let msg = if stderr.is_empty() {
                    "Fetch failed (no output)".to_string()
                } else {
                    format!("Fetch failed: {}", stderr.lines().next().unwrap_or("unknown error"))
                };
                let _ = tx.send(AppEvent::Toast {
                    message: msg,
                    is_error: true,
                });
            }
            Err(e) => {
                let _ = tx.send(AppEvent::Toast {
                    message: format!("Command error: {e}"),
                    is_error: true,
                });
            }
        }
    });
}

pub fn search_papers(tx: mpsc::UnboundedSender<AppEvent>, query: &str) {
    let query = query.to_string();
    tokio::spawn(async move {
        let output = Command::new("uv")
            .args(["run", "axp", "search", &query, "--json"])
            .output()
            .await;

        match output {
            Ok(out) if out.status.success() => {
                let stdout = String::from_utf8_lossy(&out.stdout);
                match serde_json::from_str::<Vec<ScoredPaper>>(&stdout) {
                    Ok(papers) => {
                        let _ = tx.send(AppEvent::SearchResults(papers));
                    }
                    Err(e) => {
                        let _ = tx.send(AppEvent::Toast {
                            message: format!("Parse error: {e}"),
                            is_error: true,
                        });
                    }
                }
            }
            Ok(out) => {
                let stderr = String::from_utf8_lossy(&out.stderr);
                let msg = if stderr.is_empty() {
                    "Search failed (no output)".to_string()
                } else {
                    format!("Search failed: {}", stderr.lines().next().unwrap_or("unknown error"))
                };
                let _ = tx.send(AppEvent::Toast {
                    message: msg,
                    is_error: true,
                });
            }
            Err(e) => {
                let _ = tx.send(AppEvent::Toast {
                    message: format!("Command error: {e}"),
                    is_error: true,
                });
            }
        }
    });
}
