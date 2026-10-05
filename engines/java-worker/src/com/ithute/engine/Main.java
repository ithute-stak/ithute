package com.ithute.engine;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executors;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

public final class Main {
    private static final int MAX_XML_BYTES = 10 * 1024 * 1024;

    private Main() {}

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("0.0.0.0", 8080), 128);
        server.setExecutor(Executors.newVirtualThreadPerTaskExecutor());
        server.createContext("/healthz", exchange -> {
            if (!"GET".equals(exchange.getRequestMethod())) {
                write(exchange, 405, json(Map.of("error", "method_not_allowed")));
                return;
            }
            write(exchange, 200, json(Map.of(
                "service", "ithute-java-worker",
                "engine", "java",
                "version", "0.3.0",
                "capabilities", List.of("health", "dmarc-aggregate-xml", "enterprise-xml-inspect", "push-routing-policy")
            )));
        });
        server.createContext("/v1/capabilities", exchange -> {
            if (!"GET".equals(exchange.getRequestMethod())) {
                write(exchange, 405, json(Map.of("error", "method_not_allowed")));
                return;
            }
            write(exchange, 200, json(Map.of(
                "service", "ithute-java-worker",
                "engine", "java",
                "version", "0.3.0",
                "capabilities", List.of("dmarc-aggregate-xml", "enterprise-xml-inspect", "push-routing-policy")
            )));
        });

        server.createContext("/v1/push/policy", exchange -> {
            if (!"GET".equals(exchange.getRequestMethod())) {
                write(exchange, 405, json(Map.of("error", "method_not_allowed")));
                return;
            }
            try {
                Map<String, String> query = queryParameters(exchange.getRequestURI().getRawQuery());
                String platform = lower(query.getOrDefault("platform", ""));
                boolean online = boolValue(query.get("online"));
                boolean ithuteAvailable = boolValue(query.get("ithute"));
                boolean fcmAvailable = boolValue(query.get("fcm"));
                boolean apnsAvailable = boolValue(query.get("apns"));
                boolean webpushAvailable = boolValue(query.get("webpush"));
                List<String> transports = pushTransportPolicy(
                    platform, online, ithuteAvailable, fcmAvailable, apnsAvailable, webpushAvailable
                );
                write(exchange, 200, json(Map.of(
                    "engine", "java",
                    "policy_version", "1",
                    "platform", platform,
                    "transports", transports
                )));
            } catch (IllegalArgumentException exc) {
                write(exchange, 422, json(Map.of("error", "invalid_push_policy_request")));
            }
        });

        server.createContext("/v1/dmarc/parse", exchange -> {
            if (!"POST".equals(exchange.getRequestMethod())) {
                write(exchange, 405, json(Map.of("error", "method_not_allowed")));
                return;
            }
            try {
                byte[] payload = readBounded(exchange.getRequestBody(), MAX_XML_BYTES);
                Map<String, Object> result = parseDmarc(payload);
                write(exchange, 200, json(result));
            } catch (PayloadTooLargeException exc) {
                write(exchange, 413, json(Map.of("error", "payload_too_large")));
            } catch (Exception exc) {
                write(exchange, 422, json(Map.of(
                    "error", "invalid_dmarc_report",
                    "detail", exc.getClass().getSimpleName()
                )));
            }
        });

        server.createContext("/v1/xml/inspect", exchange -> {
            if (!"POST".equals(exchange.getRequestMethod())) {
                write(exchange, 405, json(Map.of("error", "method_not_allowed")));
                return;
            }
            try {
                byte[] payload = readBounded(exchange.getRequestBody(), MAX_XML_BYTES);
                Map<String, Object> result = inspectXml(payload);
                write(exchange, 200, json(result));
            } catch (PayloadTooLargeException exc) {
                write(exchange, 413, json(Map.of("error", "payload_too_large")));
            } catch (Exception exc) {
                write(exchange, 422, json(Map.of(
                    "error", "invalid_enterprise_xml",
                    "detail", exc.getClass().getSimpleName()
                )));
            }
        });
        server.start();
        System.out.println("ithute-java-worker listening on :8080");
    }


    private static Map<String, String> queryParameters(String rawQuery) {
        Map<String, String> result = new LinkedHashMap<>();
        if (rawQuery == null || rawQuery.isBlank()) return result;
        for (String part : rawQuery.split("&")) {
            int split = part.indexOf('=');
            String rawKey = split >= 0 ? part.substring(0, split) : part;
            String rawValue = split >= 0 ? part.substring(split + 1) : "";
            String key = java.net.URLDecoder.decode(rawKey, StandardCharsets.UTF_8);
            String value = java.net.URLDecoder.decode(rawValue, StandardCharsets.UTF_8);
            result.put(key, value);
        }
        return result;
    }

    private static boolean boolValue(String value) {
        return value != null && ("1".equals(value) || "true".equalsIgnoreCase(value) || "yes".equalsIgnoreCase(value));
    }

    private static List<String> pushTransportPolicy(
        String platform,
        boolean online,
        boolean ithuteAvailable,
        boolean fcmAvailable,
        boolean apnsAvailable,
        boolean webpushAvailable
    ) {
        if (!List.of("android", "ios", "web").contains(platform)) {
            throw new IllegalArgumentException("unsupported platform");
        }
        List<String> transports = new ArrayList<>();
        if (online) transports.add("realtime");
        switch (platform) {
            case "android" -> {
                if (ithuteAvailable) transports.add("ithute");
                if (fcmAvailable) transports.add("fcm");
            }
            case "ios" -> {
                if (apnsAvailable) transports.add("apns");
            }
            case "web" -> {
                if (webpushAvailable) transports.add("webpush");
            }
            default -> throw new IllegalArgumentException("unsupported platform");
        }
        return transports;
    }

    private static byte[] readBounded(InputStream input, int limit) throws IOException, PayloadTooLargeException {
        byte[] buffer = new byte[8192];
        int total = 0;
        var out = new java.io.ByteArrayOutputStream();
        while (true) {
            int read = input.read(buffer);
            if (read < 0) break;
            total += read;
            if (total > limit) throw new PayloadTooLargeException();
            out.write(buffer, 0, read);
        }
        return out.toByteArray();
    }

    private static DocumentBuilderFactory secureFactory() throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(false);
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
        factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
        factory.setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", false);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        return factory;
    }


    private static Map<String, Object> inspectXml(byte[] payload) throws Exception {
        DocumentBuilderFactory factory = secureFactory();
        factory.setNamespaceAware(true);
        Document document = factory.newDocumentBuilder()
            .parse(new java.io.ByteArrayInputStream(payload));
        Element root = document.getDocumentElement();
        if (root == null) {
            throw new IllegalArgumentException("XML document has no root element");
        }

        int elementCount = 0;
        int attributeCount = 0;
        int textCharacters = 0;
        int maxDepth = 0;
        Map<String, Integer> elementNames = new LinkedHashMap<>();

        java.util.ArrayDeque<NodeDepth> stack = new java.util.ArrayDeque<>();
        stack.push(new NodeDepth(root, 1));
        while (!stack.isEmpty()) {
            NodeDepth current = stack.pop();
            if (!(current.node() instanceof Element element)) continue;
            elementCount++;
            if (elementCount > 100_000) {
                throw new IllegalArgumentException("XML document has too many elements");
            }
            maxDepth = Math.max(maxDepth, current.depth());
            if (maxDepth > 128) {
                throw new IllegalArgumentException("XML document nesting is too deep");
            }
            var attributes = element.getAttributes();
            for (int i = 0; i < attributes.getLength(); i++) {
                Node attribute = attributes.item(i);
                String name = attribute.getNodeName();
                String namespaceUri = attribute.getNamespaceURI();
                if ("xmlns".equals(name) || (name != null && name.startsWith("xmlns:"))
                    || XMLConstants.XMLNS_ATTRIBUTE_NS_URI.equals(namespaceUri)) {
                    continue;
                }
                attributeCount++;
            }

            String local = element.getLocalName();
            String name = (local == null || local.isBlank()) ? element.getTagName() : local;
            elementNames.merge(name, 1, Integer::sum);

            NodeList children = element.getChildNodes();
            for (int i = children.getLength() - 1; i >= 0; i--) {
                Node child = children.item(i);
                if (child instanceof Element) {
                    stack.push(new NodeDepth(child, current.depth() + 1));
                } else if (child != null && child.getNodeType() == Node.TEXT_NODE) {
                    String text = child.getNodeValue();
                    if (text != null) textCharacters += text.trim().length();
                }
            }
        }

        List<Map.Entry<String, Integer>> sorted = new ArrayList<>(elementNames.entrySet());
        sorted.sort((left, right) -> {
            int byCount = Integer.compare(right.getValue(), left.getValue());
            return byCount != 0 ? byCount : left.getKey().compareTo(right.getKey());
        });
        List<Map<String, Object>> topElements = new ArrayList<>();
        for (int i = 0; i < Math.min(20, sorted.size()); i++) {
            var entry = sorted.get(i);
            topElements.add(Map.of("name", entry.getKey(), "count", entry.getValue()));
        }

        String namespace = root.getNamespaceURI();
        String localRoot = root.getLocalName();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("engine", "java");
        result.put("parser_version", "1");
        result.put("root", (localRoot == null || localRoot.isBlank()) ? root.getTagName() : localRoot);
        result.put("namespace", namespace == null ? "" : namespace);
        result.put("element_count", elementCount);
        result.put("attribute_count", attributeCount);
        result.put("text_characters", textCharacters);
        result.put("max_depth", maxDepth);
        result.put("top_elements", topElements);
        return result;
    }

    private record NodeDepth(Node node, int depth) {}

    private static Map<String, Object> parseDmarc(byte[] payload) throws Exception {
        Document document = secureFactory().newDocumentBuilder()
            .parse(new java.io.ByteArrayInputStream(payload));
        Element root = document.getDocumentElement();
        if (root == null || !"feedback".equals(root.getTagName())) {
            throw new IllegalArgumentException("Root element must be feedback");
        }

        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("org_name", text(root, "report_metadata", "org_name"));
        metadata.put("email", text(root, "report_metadata", "email"));
        metadata.put("report_id", text(root, "report_metadata", "report_id"));
        long begin = longValue(text(root, "report_metadata", "date_range", "begin"));
        long end = longValue(text(root, "report_metadata", "date_range", "end"));
        metadata.put("begin", begin);
        metadata.put("end", end);

        Map<String, Object> policy = new LinkedHashMap<>();
        policy.put("domain", lower(text(root, "policy_published", "domain")));
        policy.put("adkim", lower(text(root, "policy_published", "adkim")));
        policy.put("aspf", lower(text(root, "policy_published", "aspf")));
        policy.put("p", lower(text(root, "policy_published", "p")));
        policy.put("sp", lower(text(root, "policy_published", "sp")));
        policy.put("pct", intValue(text(root, "policy_published", "pct"), 100));

        List<Map<String, Object>> records = new ArrayList<>();
        long total = 0;
        long passed = 0;
        long failed = 0;

        NodeList nodes = root.getElementsByTagName("record");
        for (int i = 0; i < nodes.getLength(); i++) {
            Node node = nodes.item(i);
            if (!(node instanceof Element record)) continue;

            int count = intValue(text(record, "row", "count"), 0);
            String dkim = lower(text(record, "row", "policy_evaluated", "dkim"));
            String spf = lower(text(record, "row", "policy_evaluated", "spf"));
            boolean aligned = "pass".equals(dkim) || "pass".equals(spf);

            Map<String, Object> item = new LinkedHashMap<>();
            item.put("source_ip", text(record, "row", "source_ip"));
            item.put("count", count);
            item.put("disposition", lower(text(record, "row", "policy_evaluated", "disposition")));
            item.put("dkim", dkim);
            item.put("spf", spf);
            item.put("header_from", lower(text(record, "identifiers", "header_from")));
            item.put("envelope_from", lower(text(record, "identifiers", "envelope_from")));
            item.put("dmarc_pass", aligned);
            records.add(item);

            total += Math.max(0, count);
            if (aligned) passed += Math.max(0, count);
            else failed += Math.max(0, count);
        }

        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("total_messages", total);
        summary.put("passed_messages", passed);
        summary.put("failed_messages", failed);
        summary.put("pass_rate_percent", total == 0 ? 0.0 : Math.round((passed * 10000.0 / total)) / 100.0);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("engine", "java");
        result.put("parser_version", "1");
        result.put("parsed_at", Instant.now().toString());
        result.put("metadata", metadata);
        result.put("policy", policy);
        result.put("summary", summary);
        result.put("records", records);
        return result;
    }

    private static Element child(Element parent, String name) {
        NodeList nodes = parent.getChildNodes();
        for (int i = 0; i < nodes.getLength(); i++) {
            Node node = nodes.item(i);
            if (node instanceof Element element && name.equals(element.getTagName())) {
                return element;
            }
        }
        return null;
    }

    private static String text(Element root, String... path) {
        Element current = root;
        for (String part : path) {
            current = child(current, part);
            if (current == null) return "";
        }
        String value = current.getTextContent();
        return value == null ? "" : value.trim();
    }

    private static int intValue(String value, int fallback) {
        try { return Integer.parseInt(value.trim()); } catch (Exception ignored) { return fallback; }
    }

    private static long longValue(String value) {
        try { return Long.parseLong(value.trim()); } catch (Exception ignored) { return 0L; }
    }

    private static String lower(String value) {
        return value == null ? "" : value.trim().toLowerCase(java.util.Locale.ROOT);
    }

    private static void write(HttpExchange exchange, int status, String body) throws IOException {
        byte[] data = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        exchange.getResponseHeaders().set("Cache-Control", "no-store");
        exchange.sendResponseHeaders(status, data.length);
        try (var output = exchange.getResponseBody()) {
            output.write(data);
        }
    }

    private static String json(Object value) {
        if (value == null) return "null";
        if (value instanceof String text) return quote(text);
        if (value instanceof Number || value instanceof Boolean) return value.toString();
        if (value instanceof Map<?, ?> map) {
            StringBuilder out = new StringBuilder("{");
            boolean first = true;
            for (var entry : map.entrySet()) {
                if (!first) out.append(',');
                first = false;
                out.append(quote(String.valueOf(entry.getKey()))).append(':').append(json(entry.getValue()));
            }
            return out.append('}').toString();
        }
        if (value instanceof Iterable<?> items) {
            StringBuilder out = new StringBuilder("[");
            boolean first = true;
            for (Object item : items) {
                if (!first) out.append(',');
                first = false;
                out.append(json(item));
            }
            return out.append(']').toString();
        }
        return quote(String.valueOf(value));
    }

    private static String quote(String value) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            switch (ch) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (ch < 0x20) out.append(String.format("\\u%04x", (int) ch));
                    else out.append(ch);
                }
            }
        }
        return out.append('"').toString();
    }

    private static final class PayloadTooLargeException extends Exception {}
}
