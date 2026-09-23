"""页面“填入示例”按钮使用的示例邮件头。"""

SAMPLE_HEADERS = """\
Return-Path: <sender@example.com>
Received: from mailbox.final.example (127.0.0.1)
	by mailbox.final.example (Dovecot) with LMTP id zX92kQ
	for <user@final.example>; Tue, 23 Sep 2026 10:02:10 +0800 (CST)
Received: from mx1.final.example (mx1.final.example [198.51.100.10])
	by mailbox.final.example (Postfix) with ESMTPS id 7F3A2C9
	for <user@final.example>; Tue, 23 Sep 2026 10:02:10 +0800
Received: from relay2.provider.example (relay2.provider.example [203.0.113.22])
	by mx1.final.example (Postfix) with ESMTP id B4D91
	for <user@final.example>; Tue, 23 Sep 2026 10:02:05 +0800
Received: from relay1.provider.example (relay1.provider.example
	[203.0.113.11])
	by relay2.provider.example (Postfix) with ESMTP id 99C10
	for <user@final.example>; Tue, 23 Sep 2026 02:01:55 +0000 (UTC)
Received: from outgoing.example.org (outgoing.example.org [192.0.2.50])
	by relay1.provider.example (Postfix) with ESMTP id 41AB8
	for <user@final.example>; Tue, 23 Sep 2026 02:01:30 +0000
Received: from smtp01.corp.example.net (smtp01.corp.example.net [10.10.0.5])
	by outgoing.example.org with ESMTP
	for user@final.example
Received: from [10.10.0.5] (helo=smtp01.corp.example.net)
	by smtp01.corp.example.net with ESMTP id 88FF21
	for user@final.example; not-a-valid-date (server clock lost)
Date: Tue, 23 Sep 2026 02:00:00 +0000
From: Sender <sender@example.com>
To: User <user@final.example>
Subject: Delivery path demo
	with folding
Message-ID: <demo@example.com>
"""

# 对照示例（头部 B）：与 SAMPLE_HEADERS 同一封邮件的另一条投递路径。
# 差异点：relay3.provider.example 为新增中转；relay2 的上游 IP 变化
# （身份不同 -> 原 relay2 跳记为缺失）；原本缺时间/坏时间的两跳在 B 中
# 时间有效，可演示“共有但耗时不可比较”。
SAMPLE_HEADERS_B = """\
Return-Path: <sender@example.com>
Received: from mailbox.final.example (127.0.0.1)
	by mailbox.final.example (Dovecot) with LMTP id qW81zP
	for <user@final.example>; Tue, 23 Sep 2026 10:03:20 +0800 (CST)
Received: from mx1.final.example (mx1.final.example [198.51.100.10])
	by mailbox.final.example (Postfix) with ESMTPS id 9D4E1B2
	for <user@final.example>; Tue, 23 Sep 2026 10:03:20 +0800
Received: from relay2.provider.example (relay2.provider.example [203.0.113.22])
	by mx1.final.example (Postfix) with ESMTP id C7A02
	for <user@final.example>; Tue, 23 Sep 2026 10:03:15 +0800
Received: from relay3.provider.example (relay3.provider.example [203.0.113.33])
	by relay2.provider.example (Postfix) with ESMTP id 55B77
	for <user@final.example>; Tue, 23 Sep 2026 10:03:10 +0800
Received: from relay1.provider.example (relay1.provider.example
	[203.0.113.11])
	by relay3.provider.example (Postfix) with ESMTP id 31D08
	for <user@final.example>; Tue, 23 Sep 2026 10:03:05 +0800
Received: from outgoing.example.org (outgoing.example.org [192.0.2.50])
	by relay1.provider.example (Postfix) with ESMTP id 20FB6
	for <user@final.example>; Tue, 23 Sep 2026 10:03:00 +0800
Received: from smtp01.corp.example.net (smtp01.corp.example.net [10.10.0.5])
	by outgoing.example.org with ESMTP id 77QW1
	for user@final.example; Tue, 23 Sep 2026 10:02:55 +0800
Received: from [10.10.0.5] (helo=smtp01.corp.example.net)
	by smtp01.corp.example.net with ESMTP id 12AB90
	for user@final.example; Tue, 23 Sep 2026 10:02:50 +0800
Date: Tue, 23 Sep 2026 02:02:40 +0000
From: Sender <sender@example.com>
To: User <user@final.example>
Subject: Delivery path demo
	with folding
Message-ID: <demo-alt@example.com>
"""
