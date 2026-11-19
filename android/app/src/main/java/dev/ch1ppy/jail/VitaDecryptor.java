package dev.ch1ppy.jail;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import javax.crypto.Cipher;
import javax.crypto.Mac;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/**
 * Offline PS Vita package preparation for Android.
 *
 * <p>This is a direct port of the project's {@code nativ/decrypt/vitadecrypt}
 * pipeline: it opens the user's retail PKG, unwraps the outer AES-CTR layer into
 * the NoNpDrm-style tree, then decrypts the PFS layer with the klicensee from
 * the matching {@code work.bin}/.rif. The result is the plain {@code app0} tree
 * the runtime reads. Only the Android platform crypto APIs are used, so the
 * same code can also run on a desktop JVM for verification.
 *
 * <p>SELF files are left as-is on purpose: the runtime loads game code and
 * modules from the compiled images, not from {@code eboot.bin} or the .suprx
 * helpers, so no per-title SELF decryption is needed to play.
 */
public final class VitaDecryptor {

    public interface Progress {
        void progress(String stage, long done, long total);
    }

    /* ---- fixed key material (same constants as vitadecrypt/keys.py, pfs.py) ---- */
    private static final byte[] PKG_KEY_2 = hex("e31a70c9ce1dd72bf3c0622963f2eccb");
    private static final byte[] PKG_KEY_3 = hex("423aca3a2bd5649f9686abad6fd8801f");
    private static final byte[] PKG_KEY_4 = hex("af07fd59652527baf13389668b17d9ea");

    private static final byte[] HMAC_KEY0 = hex("E462258B1F3121560745DB62B1436723D2BF80FE");
    private static final byte[] HMAC_KEY1 = hex("AFE656BB3C17256A3C809F6E9BF19FDD5A388543");
    private static final byte[] IV0 = hex("74D20CC39881C213EE770B1010E4BEA7");
    private static final byte[] CONTRACT_KEY0 = hex("E12213B48016B0E99AB81F8EC02AD4A2");

    private static final int PAGE = 0x400;
    private static final int FILE_SECTOR = 0x8000;
    private static final int SIG = 20;

    private static final int ATTR_RO = 0x0001;
    private static final int ATTR_SYS1 = 0x0002;
    private static final int ATTR_SYS2 = 0x0004;
    private static final int ATTR_AC = 0x1000;
    private static final int ATTR_NENC = 0x4000;
    private static final int ATTR_DIR = 0x8000;

    private static final int FT_NORMAL_FILE = ATTR_RO;
    private static final int FT_NORMAL_DIR = ATTR_DIR;
    private static final int FT_SYS_DIR = ATTR_DIR | ATTR_SYS1 | ATTR_SYS2;
    private static final int FT_ACID_DIR = ATTR_DIR | ATTR_AC | ATTR_SYS2;
    private static final int FT_UNENC_SYS_RW = ATTR_NENC | ATTR_SYS1 | ATTR_SYS2;
    private static final int FT_UNENC_SYS_RO = ATTR_NENC | ATTR_SYS1 | ATTR_SYS2 | ATTR_RO;
    private static final int FT_ENC_SYS_RW = ATTR_SYS1 | ATTR_SYS2;
    private static final int FT_ENC_SYS_RO = ATTR_SYS1 | ATTR_SYS2 | ATTR_RO;

    private static final long MAXVER = 0xFFFFFFFFFFFFFFFFL;

    private VitaDecryptor() {}

    /**
     * Decrypt a retail PKG into {@code outRoot/app0}. The previous app0 is only
     * replaced after the whole tree has been written and validated.
     */
    public static void decryptPkg(File pkg, File licence, File outRoot, Progress progress) throws Exception {
        if (!pkg.isFile()) throw new IOException("PKG not found: " + pkg);
        TreeInfo info = readPkgInfo(pkg);
        byte[] klic = readKlicensee(licence);

        File fs = outRoot;
        if (!fs.isDirectory() && !fs.mkdirs()) throw new IOException("cannot create " + fs);
        File part = new File(fs, "app0.part");
        File stage = new File(fs, "prepare.part");
        deleteTree(part);
        deleteTree(stage);
        if (!stage.mkdirs()) throw new IOException("cannot create " + stage);

        try {
            extractPkg(pkg, stage, info, progress);
            progress.progress("Decrypting game data", 0, 1);
            File decrypted = new File(fs, "app0.new");
            deleteTree(decrypted);
            decryptPfs(stage, klic, decrypted, progress);
            writeGameInfo(decrypted, info);
            if (!new File(decrypted, "eboot.bin").isFile() && !new File(decrypted, "PSP2_GAME").isDirectory()) {
                throw new IOException("decrypted package has no app0 content");
            }
            if (!decrypted.renameTo(part)) throw new IOException("cannot stage decrypted game data");
            deleteTree(new File(fs, "app0"));
            if (!part.renameTo(new File(fs, "app0"))) throw new IOException("cannot finish installing app0");
            progress.progress("Game data ready", 1, 1);
        } finally {
            if (System.getenv("JAIL_KEEP_STAGE") == null) deleteTree(stage);
            deleteTree(part);
        }
    }

    // ---------------------------------------------------------------------
    // PKG outer layer
    // ---------------------------------------------------------------------

    private static final class TreeInfo {
        String contentId = "";
        String titleId = "";
        long dataOffset;
        long itemsOffset;
        long fileCount;
        byte[] iv;
        byte[] mainKey;
    }

    private static TreeInfo readPkgInfo(File pkg) throws Exception {
        TreeInfo t = new TreeInfo();
        try (RandomAccessFile f = new RandomAccessFile(pkg, "r")) {
            long size = f.length();
            if (size < 0x100) throw new IOException("file is too small to be a PKG");
            byte[] head = new byte[0xC0 + 0x40];
            f.seek(0);
            f.readFully(head);

            int magic = u32be(head, 0);
            if (magic != 0x7F504B47) throw new IOException("not a Vita PKG (bad magic)");
            int infoOffset = u32be(head, 8);
            int infoCount = u32be(head, 12);
            long fileCount = u32be(head, 20);
            long totalSize = u64be(head, 24);
            long dataOffset = u64be(head, 32);
            byte[] contentId = Arrays.copyOfRange(head, 48, 96);
            byte[] iv = Arrays.copyOfRange(head, 112, 128);

            if (size < totalSize) throw new IOException("PKG is truncated");
            if (u32be(head, 0xC0) != 0x7F657874) throw new IOException("bad PKG extended header");
            int dataType2 = u32be(head, 0xC0 + 36);   /* ext header: 6 x u32, u64, 4 x u32; data_type2 is the 2nd */
            int keyType = dataType2 & 7;
            byte[] pkgKey = keyType == 2 ? PKG_KEY_2 : keyType == 3 ? PKG_KEY_3 : keyType == 4 ? PKG_KEY_4 : null;
            if (pkgKey == null) throw new IOException("unsupported PKG encryption key revision " + keyType);

            t.contentId = new String(contentId, "US-ASCII").replace("\0", "").trim();
            long sfoSize = 0;
            long sfoOffset = 0;
            for (int i = 0; i < infoCount; i++) {
                byte[] block = new byte[16];
                f.seek(infoOffset);
                f.readFully(block);
                int type = u32be(block, 0);
                int bsize = u32be(block, 4);
                if (type == 13) t.itemsOffset = u32be(block, 8) & 0xFFFFFFFFL;
                if (type == 14) { sfoOffset = u32be(block, 8) & 0xFFFFFFFFL; sfoSize = u32be(block, 12) & 0xFFFFFFFFL; }
                infoOffset += 8 + bsize;
            }
            if (sfoSize > 0 && sfoSize < 0x10000 && sfoOffset + sfoSize <= size) {
                byte[] sfo = new byte[(int) sfoSize];
                f.seek(sfoOffset);
                f.readFully(sfo);
                t.titleId = sfoString(sfo, "TITLE_ID");
                if (t.titleId.isEmpty()) t.titleId = "PCSG00615";
            } else {
                t.titleId = "PCSG00615";
            }
            if (t.contentId.isEmpty()) t.contentId = "JP0700-" + t.titleId + "_00-TOKYOGHOUL000001";

            t.dataOffset = dataOffset;
            t.fileCount = fileCount;
            t.iv = iv;
            t.mainKey = aesEcbEncryptBlock(pkgKey, iv);
        }
        return t;
    }

    private static void extractPkg(File pkg, File outDir, TreeInfo t, Progress progress) throws Exception {
        try (RandomAccessFile f = new RandomAccessFile(pkg, "r")) {
            int count = (int) t.fileCount;
            byte[] table = readRange(f, t.dataOffset + t.itemsOffset, count * 32);
            byte[] plainTable = aesCtr(t.mainKey, t.iv, t.itemsOffset / 16, table, 0, table.length);
            long total = Math.max(1, f.length());
            long done = 0;
            for (int i = 0; i < count; i++) {
                int at = i * 32;
                long nameOffset = u32be(plainTable, at) & 0xFFFFFFFFL;
                long nameSize = u32be(plainTable, at + 4) & 0xFFFFFFFFL;
                long dataOffset = u64be(plainTable, at + 8);
                long dataSize = u64be(plainTable, at + 16);
                int type = u32be(plainTable, at + 24) & 0xFF;
                if (nameSize <= 0 || nameSize > 4096) continue;
                byte[] nameCt = readRange(f, t.dataOffset + nameOffset, (int) nameSize);
                String name = new String(aesCtr(t.mainKey, t.iv, nameOffset / 16, nameCt, 0, nameCt.length), "UTF-8");
                name = sanitizeEntry(name);
                if (name == null || name.isEmpty()) continue;
                File dest = new File(outDir, name.replace('/', File.separatorChar));
                if (type == 4 || type == 18) {
                    if (!dest.mkdirs() && !dest.isDirectory()) throw new IOException("cannot create " + dest);
                    continue;
                }
                File parent = dest.getParentFile();
                if (parent != null && !parent.mkdirs() && !parent.isDirectory()) throw new IOException("cannot create " + parent);
                if (dataSize > 0x7FFFFFFFL) throw new IOException("PKG entry is too large: " + name);
                Cipher c = ctrCipher(t.mainKey, t.iv, dataOffset / 16);
                try (FileOutputStream out = new FileOutputStream(dest)) {
                    long left = dataSize;
                    long pos = t.dataOffset + dataOffset;
                    byte[] buf = new byte[1 << 20];
                    while (left > 0) {
                        int n = (int) Math.min(buf.length, left);
                        f.seek(pos);
                        f.readFully(buf, 0, n);
                        out.write(c.update(buf, 0, n));
                        pos += n; left -= n; done += n;
                    }
                    byte[] tail = c.doFinal();
                    if (tail != null && tail.length > 0) out.write(tail);
                    out.getFD().sync();
                }
                if (progress != null && (i & 7) == 0) progress.progress("Opening package", done, total);
            }
        }
    }

    private static String sanitizeEntry(String name) {
        if (name == null) return null;
        name = name.replace('\\', '/');
        while (name.startsWith("./")) name = name.substring(2);
        if (name.startsWith("/") || name.contains("\0")) return null;
        for (String part : name.split("/")) {
            if (part.equals("..")) return null;
        }
        return name;
    }

    // ---------------------------------------------------------------------
    // PFS layer
    // ---------------------------------------------------------------------

    private static final class FilesDb {
        int version;
        long filesSalt;
        int rootPage;
        byte[] rootIcv;
        byte[] secret;
        final List<Block> blocks = new ArrayList<>();
        final List<Entry> files = new ArrayList<>();
        final List<Entry> dirs = new ArrayList<>();
    }

    private static final class Block {
        int page;
        int parent;
        int type;
        int nFiles;
        final List<String> names = new ArrayList<>();
        final List<Integer> parentIdx = new ArrayList<>();
        final List<Integer> idx = new ArrayList<>();
        final List<Integer> ftype = new ArrayList<>();
        final List<Long> size = new ArrayList<>();
        final List<byte[]> hashes = new ArrayList<>();
        byte[] raw;
    }

    private static final class Entry {
        String path;
        int type;
        long size;
        int idx;
    }

    private static final class Table {
        int icvSalt;
        int version;
        int fileSector;
        byte[] dbseed;
        int sectors;
        List<byte[]> sigs = new ArrayList<>();
    }

    private static void decryptPfs(File root, byte[] klic, File outDir, Progress progress) throws Exception {
        File pfs = new File(root, "sce_pfs");
        byte[] filesDbBytes = readAll(new File(pfs, "files.db"));
        byte[] unicvBytes = readAll(new File(pfs, "unicv.db"));
        FilesDb db = parseFilesDb(filesDbBytes, klic);
        List<Table> tables = parseUnicv(unicvBytes);
        Map<String, byte[]> firstSectors = firstSectors(root);
        Map<String, Table> byPath = mapTables(tables, firstSectors, db, klic);

        if (!outDir.mkdirs() && !outDir.isDirectory()) throw new IOException("cannot create " + outDir);
        for (Entry d : db.dirs) {
            File f = new File(outDir, d.path.replace('/', File.separatorChar));
            if (!f.mkdirs() && !f.isDirectory()) throw new IOException("cannot create " + f);
        }
        int done = 0;
        for (Entry e : db.files) {
            File src = new File(root, e.path.replace('/', File.separatorChar));
            File dst = new File(outDir, e.path.replace('/', File.separatorChar));
            File parent = dst.getParentFile();
            if (parent != null && !parent.mkdirs() && !parent.isDirectory()) throw new IOException("cannot create " + parent);
            if (e.size == 0) { new FileOutputStream(dst).close(); continue; }
            Table t = byPath.get(e.path);
            if (t == null) throw new IOException("no PFS table for " + e.path);
            if (e.type == FT_UNENC_SYS_RW || e.type == FT_UNENC_SYS_RO) {
                decryptFile(src, dst, t, db, klic, false, e.size);
            } else if (e.type == FT_NORMAL_FILE || e.type == FT_ENC_SYS_RW || e.type == FT_ENC_SYS_RO) {
                decryptFile(src, dst, t, db, klic, true, e.size);
            } else {
                throw new IOException("unexpected PFS file type for " + e.path);
            }
            if (progress != null && (++done % 8) == 0) progress.progress("Decrypting game data", done, db.files.size());
        }
    }

    private static FilesDb parseFilesDb(byte[] db, byte[] klic) throws Exception {
        if (db.length < PAGE) throw new IOException("files.db is truncated");
        if (!new String(Arrays.copyOfRange(db, 0, 8), "US-ASCII").equals("SCENGPFS"))
            throw new IOException("files.db: bad magic");
        FilesDb f = new FilesDb();
        f.version = u32le(db, 8);
        int imageSpec = u16le(db, 12);
        int keyId = u16le(db, 14);
        int pageSize = u32le(db, 16);
        int btOrder = u32le(db, 20);
        f.rootPage = u32le(db, 24);
        f.filesSalt = u32le(db, 28) & 0xFFFFFFFFL;
        long unk6 = u64le(db, 32);
        long tailSize = u64le(db, 40);
        f.rootIcv = Arrays.copyOfRange(db, 56, 76);
        byte[] headerIcv = Arrays.copyOfRange(db, 76, 96);
        if (f.version < 3 || f.version > 5) throw new IOException("files.db: unexpected version " + f.version);
        if (imageSpec != 1 && imageSpec != 4) throw new IOException("files.db: unsupported image spec");
        if (keyId != 0 || pageSize != PAGE || btOrder != 0xA || unk6 != -1L)
            throw new IOException("files.db: unexpected header");
        if (tailSize != db.length - PAGE) throw new IOException("files.db: size mismatch");
        for (int i = 608; i < PAGE; i++) if (db[i] != 0) throw new IOException("files.db: bad header padding");

        f.secret = deriveSecret(klic, f.filesSalt, 0);
        byte[] sig = Arrays.copyOf(db, 0x160);
        Arrays.fill(sig, 76, 96, (byte)0);
        Arrays.fill(sig, 96, 352, (byte)0);
        if (!Arrays.equals(hmac(f.secret, sig), headerIcv)) throw new IOException("work.bin does not match this PKG (files.db signature)");

        int order = orderMax(PAGE);
        Map<Integer, Block> byPage = new HashMap<>();
        for (int pos = PAGE; pos < db.length; pos += PAGE) {
            if (pos + PAGE > db.length) throw new IOException("files.db: truncated page");
            Block b = parseBlock(db, pos, f.version == 5);
            f.blocks.add(b);
            byPage.put(b.page, b);
            if (b.type > 1) throw new IOException("files.db: bad block type");
            for (int i = 0; i < b.nFiles; i++) {
                if (b.idx.get(i) == -1) continue;
                Entry e = new Entry();
                e.idx = b.idx.get(i);
                e.type = b.ftype.get(i);
                e.size = b.size.get(i);
                e.path = "";
            }
        }
        Block root = byPage.get(f.rootPage);
        if (root == null) throw new IOException("files.db: root page is missing");
        if (!Arrays.equals(nodeIcv(f.secret, f.version, order, root), f.rootIcv))
            throw new IOException("work.bin does not match this PKG (root signature)");

        Map<Integer, List<Block>> byParent = new HashMap<>();
        Set<Integer> parents = new HashSet<>();
        for (Block b : f.blocks) {
            byParent.computeIfAbsent(b.parent, k -> new ArrayList<>()).add(b);
            parents.add(b.parent);
        }
        verifyTree(root, byParent, f.secret, f.version, order);

        Map<Integer, int[]> flat = new HashMap<>();   // idx -> parent,type,size
        Map<Integer, String> names = new HashMap<>();
        /* Two passes: every leaf entry has to be known before a path can be
           walked, because a directory may live in a later page than its child. */
        for (Block b : f.blocks) {
            if (parents.contains(b.page)) continue;
            for (int i = 0; i < b.nFiles; i++) {
                int idx = b.idx.get(i);
                if (idx == -1) continue;
                flat.put(idx, new int[]{b.parentIdx.get(i), b.ftype.get(i), (int) Math.min(Integer.MAX_VALUE, b.size.get(i))});
                names.put(idx, b.names.get(i));
            }
        }
        for (Map.Entry<Integer, int[]> it : flat.entrySet()) {
            int idx = it.getKey();
            int[] v = it.getValue();
            Entry e = new Entry();
            e.idx = idx; e.type = v[1]; e.size = v[2];
            e.path = fullPath(idx, flat, names);
            if (isDir(e.type)) f.dirs.add(e); else f.files.add(e);
        }
        return f;
    }

    private static Block parseBlock(byte[] db, int pos, boolean version5) throws IOException {
        Block b = new Block();
        b.raw = Arrays.copyOfRange(db, pos, pos + PAGE);
        b.page = (pos - PAGE) / PAGE;
        b.parent = u32le(b.raw, 0);
        b.type = u32le(b.raw, 4);
        b.nFiles = u32le(b.raw, 8);
        if (u32le(b.raw, 12) != 0) throw new IOException("files.db: bad block padding");
        if (b.nFiles > 9) throw new IOException("files.db: too many files in a block");
        for (int i = 0; i < 9; i++) {
            int at = 16 + i * 72;
            int idx = u32le(b.raw, at);
            String name = cString(b.raw, at + 4, 68);
            if (i < b.nFiles) { b.parentIdx.add(idx); b.names.add(name); }
            else for (int k = 0; k < 72; k++) if (b.raw[at + k] != 0) throw new IOException("files.db: bad unused name slot");
        }
        for (int i = 0; i < 10; i++) {
            int at = 664 + i * 16;
            int idx = u32le(b.raw, at);
            int type = u16le(b.raw, at + 4);
            int pad0 = u16le(b.raw, at + 6);
            long size = u32le(b.raw, at + 8) & 0xFFFFFFFFL;
            int pad1 = u32le(b.raw, at + 12);
            if (pad0 != 0 || pad1 != 0) throw new IOException("files.db: bad file info padding");
            if (i < b.nFiles) { b.idx.add(idx); b.ftype.add(type); b.size.add(size); }
        }
        for (int i = 0; i < 10; i++) b.hashes.add(Arrays.copyOfRange(b.raw, 824 + i * SIG, 824 + (i + 1) * SIG));
        return b;
    }

    private static void verifyTree(Block block, Map<Integer, List<Block>> byParent, byte[] secret, int version, int order) throws Exception {
        List<Block> kids = byParent.get(block.page);
        if (kids == null) return;
        int slots = block.nFiles + (block.type > 0 ? 1 : 0);
        for (Block child : kids) {
            byte[] icv = nodeIcv(secret, version, order, child);
            boolean found = false;
            for (int i = 0; i < slots; i++) if (Arrays.equals(icv, block.hashes.get(i))) { found = true; break; }
            if (!found) throw new IOException("files.db: hash tree mismatch (wrong work.bin or corrupt PKG)");
            verifyTree(child, byParent, secret, version, order);
        }
    }

    private static byte[] nodeIcv(byte[] secret, int version, int order, Block b) throws Exception {
        if (version == 5) {
            int size = 0x6C * order - 0x3C;
            return hmac(secret, Arrays.copyOfRange(b.raw, 4, 4 + size));
        }
        int slots = b.nFiles + (b.type > 0 ? 1 : 0);
        byte[] icv = new byte[SIG];
        for (int i = 0; i < slots; i++) {
            byte[] msg = new byte[SIG * 2];
            System.arraycopy(icv, 0, msg, 0, SIG);
            System.arraycopy(b.hashes.get(i), 0, msg, SIG, SIG);
            icv = hmac(secret, msg);
        }
        return icv;
    }

    private static String fullPath(int idx, Map<Integer, int[]> flat, Map<Integer, String> names) throws IOException {
        List<String> parts = new ArrayList<>();
        Set<Integer> seen = new HashSet<>();
        int cur = idx;
        while (cur != 0) {
            if (!seen.add(cur)) throw new IOException("files.db: cyclic directory chain");
            int[] v = flat.get(cur);
            if (v == null) throw new IOException("files.db: missing directory idx=" + cur + " for " + idx + " (" + names.get(idx) + ")");
            parts.add(names.get(cur));
            cur = v[0];
        }
        StringBuilder sb = new StringBuilder();
        for (int i = parts.size() - 1; i >= 0; i--) {
            if (parts.get(i).isEmpty()) continue;
            if (sb.length() > 0) sb.append('/');
            sb.append(parts.get(i));
        }
        return sb.toString();
    }

    private static List<Table> parseUnicv(byte[] db) throws IOException {
        if (db.length < PAGE) throw new IOException("unicv.db is truncated");
        if (!new String(Arrays.copyOfRange(db, 0, 8), "US-ASCII").equals("SCEIRODB"))
            throw new IOException("unicv.db: bad magic");
        long dataSize = u64le(db, 24);
        if (u32le(db, 12) != PAGE || u32le(db, 16) != -1 || u32le(db, 20) != -1 || db.length != dataSize + PAGE)
            throw new IOException("unicv.db: bad header");
        List<Table> out = new ArrayList<>();
        int pos = PAGE;
        int binMax = (PAGE - 16) / SIG;
        while (pos < db.length) {
            byte[] page = Arrays.copyOfRange(db, pos, pos + PAGE);
            boolean blank = true;
            for (byte v : page) if (v != 0) { blank = false; break; }
            if (blank) { pos += PAGE; continue; }
            if (!new String(Arrays.copyOfRange(page, 0, 8), "US-ASCII").equals("SCEIFTBL"))
                throw new IOException("unicv.db: bad table magic");
            Table t = new Table();
            t.version = u32le(page, 8);
            if (u32le(page, 12) != PAGE || u32le(page, 16) != binMax || u32le(page, 24) != FILE_SECTOR)
                throw new IOException("unicv.db: bad table header");
            t.sectors = u32le(page, 20);
            t.icvSalt = pos / PAGE;
            t.fileSector = u32le(page, 24);
            if (t.version != 1 && t.version != 2) throw new IOException("unicv.db: bad table version");
            if (t.version == 2) t.dbseed = Arrays.copyOfRange(page, 52, 72);
            for (int i = 28; i < 32; i++) if (page[i] != 0) throw new IOException("unicv.db: bad padding");
            for (int i = 72; i < PAGE; i++) if (page[i] != 0) throw new IOException("unicv.db: bad padding");
            pos += PAGE;
            int left = t.sectors;
            while (left > 0) {
                byte[] sp = Arrays.copyOfRange(db, pos, pos + PAGE);
                int n = Math.min(left, binMax);
                if (u32le(sp, 0) != binMax * SIG + 16 || u32le(sp, 4) != SIG || u32le(sp, 8) != n || u32le(sp, 12) != 0)
                    throw new IOException("unicv.db: bad signature page");
                for (int i = 0; i < n; i++) t.sigs.add(Arrays.copyOfRange(sp, 16 + i * SIG, 16 + (i + 1) * SIG));
                for (int i = 16 + n * SIG; i < PAGE; i++) if (sp[i] != 0) throw new IOException("unicv.db: bad signature padding");
                pos += PAGE;
                left -= n;
            }
            out.add(t);
        }
        return out;
    }

    private static Map<String, byte[]> firstSectors(File root) throws IOException {
        Map<String, byte[]> out = new HashMap<>();
        scan(root, "", out);
        return out;
    }

    private static void scan(File dir, String rel, Map<String, byte[]> out) throws IOException {
        File[] files = dir.listFiles();
        if (files == null) return;
        for (File f : files) {
            String path = rel.isEmpty() ? f.getName() : rel + "/" + f.getName();
            if (f.isDirectory()) {
                if (path.equals("sce_pfs") || path.startsWith("sce_pfs/")) continue;
                if (path.equals("sce_sys")) {
                    File[] kids = f.listFiles();
                    if (kids != null) for (File k : kids) {
                        if (k.isDirectory() && k.getName().equals("package")) continue;
                        String p = path + "/" + k.getName();
                        if (k.isDirectory()) scan(k, p, out);
                        else out.put(p, firstSector(k));
                    }
                    continue;
                }
                scan(f, path, out);
            } else {
                out.put(path, firstSector(f));
            }
        }
    }

    private static byte[] firstSector(File f) throws IOException {
        try (FileInputStream in = new FileInputStream(f)) {
            byte[] buf = new byte[FILE_SECTOR];
            int n = 0, r;
            while (n < buf.length && (r = in.read(buf, n, buf.length - n)) > 0) n += r;
            return Arrays.copyOf(buf, n);
        }
    }

    private static Map<String, Table> mapTables(List<Table> tables, Map<String, byte[]> files, FilesDb db, byte[] klic) throws Exception {
        Map<String, Table> out = new HashMap<>();
        Map<String, byte[]> left = new HashMap<>(files);
        for (Table t : tables) {
            if (t.sectors == 0 || t.sigs.isEmpty()) continue;
            byte[] secret = deriveSecret(klic, db.filesSalt, t.icvSalt);
            byte[] sigKey = hmac(secret, le32(0));
            byte[] target = t.sigs.get(0);
            String found = null;
            for (Map.Entry<String, byte[]> e : left.entrySet()) {
                if (Arrays.equals(hmac(sigKey, e.getValue()), target)) { found = e.getKey(); break; }
            }
            if (found == null) throw new IOException("unicv.db: no file matches a PFS table (wrong work.bin)");
            out.put(found, t);
            left.remove(found);
        }
        return out;
    }

    private static void decryptFile(File src, File dst, Table t, FilesDb db, byte[] klic, boolean encrypted, long size) throws Exception {
        byte[] secret = deriveSecret(klic, db.filesSalt, t.icvSalt);
        byte[] drv = aesEcbDecryptBlock(CONTRACT_KEY0, klic);
        byte[] tweakKey;
        if (t.dbseed != null) {
            tweakKey = Arrays.copyOf(hmac(HMAC_KEY0, t.dbseed), 16);
        } else {
            byte[] msg = db.filesSalt == 0 ? le32(t.icvSalt) : concat(le32(db.filesSalt), le32(t.icvSalt));
            tweakKey = Arrays.copyOf(hmac(HMAC_KEY0, msg), 16);
        }
        try (RandomAccessFile in = new RandomAccessFile(src, "r");
             FileOutputStream out = new FileOutputStream(dst)) {
            long len = in.length();
            int sectors = (int) ((len + FILE_SECTOR - 1) / FILE_SECTOR);
            if (sectors != t.sectors) throw new IOException("PFS sector count mismatch for " + src.getName());
            byte[] chunk = new byte[FILE_SECTOR];
            long written = 0;
            for (int i = 0; i < sectors; i++) {
                int n = (int) Math.min(FILE_SECTOR, len - (long) i * FILE_SECTOR);
                in.readFully(chunk, 0, n);
                byte[] data = Arrays.copyOf(chunk, n);
                byte[] sigKey = hmac(secret, le32(i));
                if (!Arrays.equals(hmac(sigKey, data), t.sigs.get(i)))
                    throw new IOException("PFS integrity check failed for " + src.getName());
                byte[] plain;
                if (encrypted) {
                    byte[] tweak = new byte[16];
                    long off = (long) FILE_SECTOR * i;
                    for (int b = 0; b < 8; b++) tweak[b] = (byte) (off >>> (8 * b));
                    for (int b = 0; b < 16; b++) tweak[b] ^= tweakKey[b];
                    plain = cbcCts(drv, tweak, data, false);
                } else {
                    plain = data;
                }
                int take = (int) Math.min(plain.length, size - written);
                if (take > 0) { out.write(plain, 0, take); written += take; }
                if (written >= size) break;
            }
            out.getFD().sync();
        }
    }

    private static boolean isDir(int type) {
        return type == FT_NORMAL_DIR || type == FT_SYS_DIR || type == FT_ACID_DIR;
    }

    private static void writeGameInfo(File dir, TreeInfo t) throws IOException {
        String json = "{\n"
                + "  \"title_id\": \"" + t.titleId + "\",\n"
                + "  \"content_id\": \"" + t.contentId + "\",\n"
                + "  \"source\": \"pkg\"\n"
                + "}\n";
        try (FileOutputStream out = new FileOutputStream(new File(dir, "game.json"))) {
            out.write(json.getBytes("UTF-8"));
        }
    }

    // ---------------------------------------------------------------------
    // Crypto helpers
    // ---------------------------------------------------------------------

    private static byte[] deriveSecret(byte[] klic, long filesSalt, long icvSalt) throws Exception {
        byte[] msg = filesSalt == 0 ? le32(icvSalt) : concat(le32(filesSalt), le32(icvSalt));
        byte[] combo = hmac(HMAC_KEY1, msg);
        byte[] drv = aesEcbDecryptBlock(CONTRACT_KEY0, klic);
        return cbcCts(drv, IV0, combo, true);
    }

    private static byte[] cbcCts(byte[] key, byte[] iv, byte[] data, boolean encrypt) throws Exception {
        int full = data.length & ~15;
        int tail = data.length & 15;
        byte[] out = new byte[data.length];
        byte[] chain = iv;
        if (full > 0) {
            Cipher c = Cipher.getInstance("AES/CBC/NoPadding");
            c.init(encrypt ? Cipher.ENCRYPT_MODE : Cipher.DECRYPT_MODE, new SecretKeySpec(key, "AES"), new IvParameterSpec(iv));
            byte[] block = c.doFinal(data, 0, full);
            System.arraycopy(block, 0, out, 0, full);
            chain = encrypt ? Arrays.copyOfRange(block, full - 16, full) : Arrays.copyOfRange(data, full - 16, full);
        }
        if (tail > 0) {
            byte[] mask = aesEcbEncryptBlock(key, chain);
            for (int i = 0; i < tail; i++) out[full + i] = (byte) (data[full + i] ^ mask[i]);
        }
        return out;
    }

    private static byte[] aesEcbEncryptBlock(byte[] key, byte[] block) throws Exception {
        Cipher c = Cipher.getInstance("AES/ECB/NoPadding");
        c.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(key, "AES"));
        return c.doFinal(block);
    }

    private static byte[] aesEcbDecryptBlock(byte[] key, byte[] block) throws Exception {
        Cipher c = Cipher.getInstance("AES/ECB/NoPadding");
        c.init(Cipher.DECRYPT_MODE, new SecretKeySpec(key, "AES"));
        return c.doFinal(block);
    }

    private static Cipher ctrCipher(byte[] key, byte[] iv, long blocks) throws Exception {
        byte[] ctr = addBlocks(iv, blocks);
        Cipher c = Cipher.getInstance("AES/CTR/NoPadding");
        c.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(key, "AES"), new IvParameterSpec(ctr));
        return c;
    }

    private static byte[] aesCtr(byte[] key, byte[] iv, long blocks, byte[] data, int off, int len) throws Exception {
        Cipher c = ctrCipher(key, iv, blocks);
        return c.doFinal(data, off, len);
    }

    private static byte[] addBlocks(byte[] iv, long blocks) {
        byte[] out = iv.clone();
        long add = blocks;
        for (int i = 15; i >= 0 && add != 0; i--) {
            long sum = (out[i] & 0xFFL) + (add & 0xFFL);
            out[i] = (byte) sum;
            add = (add >>> 8) + (sum >>> 8);
        }
        return out;
    }

    private static byte[] hmac(byte[] key, byte[] data) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA1");
        mac.init(new SecretKeySpec(key, "HmacSHA1"));
        return mac.doFinal(data);
    }

    /**
     * Read the 16-byte klicensee from a 512-byte RIF/work.bin. The layout is
     * little-endian: version/flags (8), aid (8), content id (48), key table
     * (16), then the key at offset 80.
     */
    static byte[] readKlicensee(File licence) throws IOException {
        byte[] data = readAll(licence);
        if (data.length == 1024) data = Arrays.copyOf(data, 512);
        if (data.length != 512) throw new IOException("work.bin must be 512 bytes");
        byte[] key = Arrays.copyOfRange(data, 80, 96);
        boolean zero = true;
        for (byte b : key) if (b != 0) { zero = false; break; }
        if (zero) throw new IOException("work.bin has no klicensee");
        return key;
    }

    // ---------------------------------------------------------------------
    // Small helpers
    // ---------------------------------------------------------------------

    private static int orderMax(int pageSize) {
        int index = 1;
        while (pageSize > 108 * index - 56) index++;
        if (pageSize < 108 * index - 56) index--;
        return index;
    }

    private static String cString(byte[] data, int off, int max) {
        int end = off;
        while (end < off + max && data[end] != 0) end++;
        return new String(data, off, end - off, java.nio.charset.StandardCharsets.UTF_8);
    }

    private static String sfoString(byte[] sfo, String key) {
        byte[] k = key.getBytes(java.nio.charset.StandardCharsets.US_ASCII);
        for (int i = 0; i + k.length + 4 <= sfo.length; i++) {
            boolean match = true;
            for (int j = 0; j < k.length; j++) if (sfo[i + j] != k[j]) { match = false; break; }
            if (!match) continue;
            int at = i + k.length;
            while (at + 4 <= sfo.length && at < i + 64) {
                int len = u32le(sfo, at);
                if (len > 0 && len < 128 && at + 4 + len <= sfo.length) {
                    boolean ascii = true;
                    for (int x = 0; x < len; x++) { int c = sfo[at + 4 + x] & 0xFF; if (c != 0 && c < 0x20) { ascii = false; break; } }
                    if (ascii) return new String(sfo, at + 4, len, java.nio.charset.StandardCharsets.US_ASCII).replace("\0", "");
                }
                at++;
            }
        }
        return "";
    }

    private static byte[] readRange(RandomAccessFile f, long pos, int len) throws IOException {
        byte[] out = new byte[len];
        f.seek(pos);
        f.readFully(out);
        return out;
    }

    private static byte[] readAll(File f) throws IOException {
        try (FileInputStream in = new FileInputStream(f)) {
            long n = f.length();
            if (n > Integer.MAX_VALUE) throw new IOException("file is too large: " + f);
            byte[] out = new byte[(int) n];
            int at = 0;
            while (at < out.length) {
                int r = in.read(out, at, out.length - at);
                if (r < 0) throw new IOException("short read: " + f);
                at += r;
            }
            return out;
        }
    }

    private static void deleteTree(File f) {
        if (f == null || !f.exists()) return;
        File[] kids = f.listFiles();
        if (kids != null) for (File k : kids) deleteTree(k);
        f.delete();
    }

    private static int u16le(byte[] b, int o) { return (b[o] & 0xFF) | (b[o + 1] & 0xFF) << 8; }
    private static int u32le(byte[] b, int o) { return (b[o] & 0xFF) | (b[o + 1] & 0xFF) << 8 | (b[o + 2] & 0xFF) << 16 | (b[o + 3] & 0xFF) << 24; }
    private static long u64le(byte[] b, int o) { return (u32le(b, o) & 0xFFFFFFFFL) | ((long) u32le(b, o + 4) << 32); }
    private static int u32be(byte[] b, int o) { return (b[o] & 0xFF) << 24 | (b[o + 1] & 0xFF) << 16 | (b[o + 2] & 0xFF) << 8 | (b[o + 3] & 0xFF); }
    private static long u64be(byte[] b, int o) { return ((long) u32be(b, o) << 32) | (u32be(b, o + 4) & 0xFFFFFFFFL); }
    private static byte[] le32(long v) { return new byte[]{(byte) v, (byte) (v >>> 8), (byte) (v >>> 16), (byte) (v >>> 24)}; }

    private static byte[] concat(byte[] a, byte[] b) {
        byte[] out = new byte[a.length + b.length];
        System.arraycopy(a, 0, out, 0, a.length);
        System.arraycopy(b, 0, out, a.length, b.length);
        return out;
    }

    private static byte[] hex(String s) {
        int n = s.length() / 2;
        byte[] out = new byte[n];
        for (int i = 0; i < n; i++) out[i] = (byte) Integer.parseInt(s.substring(2 * i, 2 * i + 2), 16);
        return out;
    }

    /** Host-side entry point used by the verification script. */
    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.err.println("usage: VitaDecryptor <pkg> <work.bin> <out dir>");
            System.exit(2);
        }
        decryptPkg(new File(args[0]), new File(args[1]), new File(args[2]), new Progress() {
            @Override public void progress(String stage, long done, long total) {
                if (total > 0 && (done == 0 || done == total || done % (64L << 20) == 0)) {
                    System.err.println(stage + ": " + (done * 100 / total) + "%");
                }
            }
        });
    }
}
