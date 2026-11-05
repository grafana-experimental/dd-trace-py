#include <echion/strings.h>

std::unique_ptr<unsigned char[]>
pybytes_to_bytes_and_size(PyObject* bytes_addr, Py_ssize_t* size)
{
    // Pyroscope patch: small bytes objects do not include the struct padding.
    PyVarObject bytes;

    if (copy_type(bytes_addr, bytes))
        return nullptr;

    *size = bytes.ob_size;
    if (*size < 0 || *size > MAX_STRING_SIZE)
        return nullptr;

    auto data = std::make_unique<unsigned char[]>(*size);
    if (copy_generic(reinterpret_cast<char*>(bytes_addr) + offsetof(PyBytesObject, ob_sval), data.get(), *size))
        return nullptr;

    return data;
}
Result<std::string>
pyunicode_to_utf8(PyObject* str_addr)
{
    // Pyroscope patch: compact ASCII strings only allocate PyASCIIObject plus
    // their bytes. Copying a full PyUnicodeObject overreads short strings.
    PyASCIIObject ascii;
    if (copy_type(str_addr, ascii))
        return ErrorKind::PyUnicodeError;

    if (ascii.state.kind != 1)
        return ErrorKind::PyUnicodeError;

    const char* data;
    Py_ssize_t size;
    if (ascii.state.compact && ascii.state.ascii) {
        data = reinterpret_cast<const char*>(str_addr) + sizeof(ascii);
        size = ascii.length;
    } else {
        PyCompactUnicodeObject compact;
        if (copy_type(str_addr, compact))
            return ErrorKind::PyUnicodeError;
        data = compact.utf8;
        size = compact.utf8_length;
    }
    if (data == nullptr)
        return ErrorKind::PyUnicodeError;

    if (size < 0 || size > 1024)
        return ErrorKind::PyUnicodeError;

    auto dest = std::string(size, '\0');
    if (copy_generic(data, dest.data(), size))
        return ErrorKind::PyUnicodeError;

    return Result<std::string>(dest);
}

[[nodiscard]] Result<StringTable::Key>
StringTable::key(PyObject* s, StringTag tag)
{
    const std::lock_guard<std::mutex> lock(table_lock);

    auto k = make_tagged_key(reinterpret_cast<uintptr_t>(s), tag);

    if (table_.find(k) == table_.end()) {
        auto maybe_unicode = pyunicode_to_utf8(s);
        if (!maybe_unicode) {
            return ErrorKind::PyUnicodeError;
        }

        table_.emplace(k, std::move(*maybe_unicode));
    }

    return Result<Key>(k);
}

[[nodiscard]] Result<std::reference_wrapper<const std::string>>
StringTable::lookup(StringTable::Key key) const
{
    const std::lock_guard<std::mutex> lock(table_lock);

    const auto it = table_.find(key);
    if (it == table_.cend())
        return ErrorKind::LookupError;

    return std::ref(it->second);
}
