use tokio::process::Command;
use tokio::sync::mpsc;

use crate::app::AppEvent;

pub fn run_summarize(tx: mpsc::UnboundedSender<AppEvent>, job_id: String, arxiv_id: String) {
    tokio::spawn(async move {
        let output = Command::new("uv")
            .args(["run", "axp", "show", &arxiv_id, "--summary", "--force"])
            .output()
            .await;

        match output {
            Ok(out) if out.status.success() => {
                let _ = tx.send(AppEvent::JobCompleted {
                    job_id,
                    message: format!("Summary ready for {arxiv_id}"),
                });
            }
            Ok(out) => {
                let stderr = String::from_utf8_lossy(&out.stderr);
                let msg = stderr
                    .lines()
                    .next()
                    .unwrap_or("Summarize failed")
                    .to_string();
                let _ = tx.send(AppEvent::JobFailed { job_id, message: msg });
            }
            Err(e) => {
                let _ = tx.send(AppEvent::JobFailed {
                    job_id,
                    message: format!("Command error: {e}"),
                });
            }
        }
    });
}

pub fn run_translate(tx: mpsc::UnboundedSender<AppEvent>, job_id: String, arxiv_id: String) {
    tokio::spawn(async move {
        let output = Command::new("uv")
            .args(["run", "axp", "translate", &arxiv_id, "--force"])
            .output()
            .await;

        match output {
            Ok(out) if out.status.success() => {
                let _ = tx.send(AppEvent::JobCompleted {
                    job_id,
                    message: format!("Translation ready for {arxiv_id}"),
                });
            }
            Ok(out) => {
                let stderr = String::from_utf8_lossy(&out.stderr);
                let msg = stderr
                    .lines()
                    .next()
                    .unwrap_or("Translate failed")
                    .to_string();
                let _ = tx.send(AppEvent::JobFailed { job_id, message: msg });
            }
            Err(e) => {
                let _ = tx.send(AppEvent::JobFailed {
                    job_id,
                    message: format!("Command error: {e}"),
                });
            }
        }
    });
}

pub fn run_review(tx: mpsc::UnboundedSender<AppEvent>, job_id: String, arxiv_id: String) {
    tokio::spawn(async move {
        let output = Command::new("uv")
            .args(["run", "axp", "review", &arxiv_id, "--force"])
            .output()
            .await;

        match output {
            Ok(out) if out.status.success() => {
                let _ = tx.send(AppEvent::JobCompleted {
                    job_id,
                    message: format!("Review ready for {arxiv_id}"),
                });
            }
            Ok(out) => {
                let stderr = String::from_utf8_lossy(&out.stderr);
                let msg = stderr
                    .lines()
                    .next()
                    .unwrap_or("Review failed")
                    .to_string();
                let _ = tx.send(AppEvent::JobFailed { job_id, message: msg });
            }
            Err(e) => {
                let _ = tx.send(AppEvent::JobFailed {
                    job_id,
                    message: format!("Command error: {e}"),
                });
            }
        }
    });
}
