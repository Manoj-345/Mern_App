import { createContext, useEffect, useState } from "react";
import axios from "axios";
import toast from "react-hot-toast";
import { io } from "socket.io-client";

// ✅ Use SAME domain (handled by Ingress)
axios.defaults.baseURL = "/";

export const AuthContext = createContext();

export const AuthProvider = ({ children }) => {

    const [token, setToken] = useState(localStorage.getItem("token"));
    const [authUser, setAuthUser] = useState(null);
    const [onlineUsers, setOnlineUsers] = useState([]);
    const [socket, setSocket] = useState(null);

    // ✅ CHECK AUTH
    const checkAuth = async () => {
        try {
            const { data } = await axios.get("/api/auth/check");
            if (data.success) {
                setAuthUser(data.user);
                connectSocket(data.user);
            }
        } catch (error) {
            toast.error(error?.response?.data?.message || error.message);
        }
    };

    // ✅ LOGIN
    const login = async (state, credentials) => {
        try {
            const { data } = await axios.post(`/api/auth/${state}`, credentials);

            if (data.success) {
                setAuthUser(data.userData);

                axios.defaults.headers.common["token"] = data.token;
                setToken(data.token);
                localStorage.setItem("token", data.token);

                connectSocket(data.userData);

                toast.success(data.message);
            } else {
                toast.error(data.message);
            }
        } catch (error) {
            toast.error(error?.response?.data?.message || error.message);
        }
    };

    // ✅ LOGOUT
    const logout = () => {
        localStorage.removeItem("token");
        setToken(null);
        setAuthUser(null);
        setOnlineUsers([]);

        axios.defaults.headers.common["token"] = null;

        if (socket) socket.disconnect();

        toast.success("Logged out successfully");
    };

    // ✅ UPDATE PROFILE
    const updateProfile = async (body) => {
        try {
            const { data } = await axios.put("/api/auth/update-profile", body);
            if (data.success) {
                setAuthUser(data.user);
                toast.success("Profile updated successfully");
            }
        } catch (error) {
            toast.error(error?.response?.data?.message || error.message);
        }
    };

    // ✅ SOCKET CONNECTION (IMPORTANT)
    const connectSocket = (userData) => {
        if (!userData || socket?.connected) return;

        const newSocket = io({
            path: "/socket.io",
            transports: ["websocket"],
            query: {
                userId: userData._id,
            },
        });

        setSocket(newSocket);

        newSocket.on("connect", () => {
            console.log("Socket connected:", newSocket.id);
        });

        newSocket.on("getOnlineUsers", (users) => {
            setOnlineUsers(users);
        });

        newSocket.on("disconnect", () => {
            console.log("Socket disconnected");
        });
    };

    useEffect(() => {
        if (token) {
            axios.defaults.headers.common["token"] = token;
            checkAuth();
        }
    }, [token]);

    const value = {
        axios,
        authUser,
        onlineUsers,
        socket,
        login,
        logout,
        updateProfile,
    };

    return (
        <AuthContext.Provider value={value}>
            {children}
        </AuthContext.Provider>
    );
};