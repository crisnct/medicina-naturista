() => {
    const scrollToLatestMessage = () => {
        const chat = document.getElementById("medical-chatbot");
        const messages = chat?.querySelectorAll('[data-testid="bot"], [data-testid="user"], .message');
        const latest = messages?.length ? messages[messages.length - 1] : chat?.lastElementChild;
        if (latest) {
            latest.scrollIntoView({behavior: "smooth", block: "end"});
        } else {
            window.scrollTo({top: document.documentElement.scrollHeight, behavior: "smooth"});
        }
    };
    requestAnimationFrame(() => setTimeout(scrollToLatestMessage, 80));
}
